"use client";

import { Search } from "lucide-react";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { listFacilities, type FacilityListResponse } from "@/lib/api";
import { queryString } from "@/lib/query";

export type DirectoryFilterParams = Record<string, string | undefined>;

type DirectorySearchValue = {
  query: string;
  input: string;
  result: FacilityListResponse | null;
  error: string | null;
  isSearching: boolean;
  setInput: (value: string) => void;
  submit: () => void;
};

const DirectorySearchContext = createContext<DirectorySearchValue | null>(null);

const SEARCH_DEBOUNCE_MS = 350;

export function useDirectorySearch() {
  const value = useContext(DirectorySearchContext);
  if (!value) {
    throw new Error("useDirectorySearch must be used inside DirectorySearchProvider");
  }
  return value;
}

export function DirectorySearchProvider({
  initialQuery,
  initialResult,
  initialError,
  filterParams,
  children,
}: {
  initialQuery: string;
  initialResult: FacilityListResponse | null;
  initialError: string | null;
  filterParams: DirectoryFilterParams;
  children: ReactNode;
}) {
  const [input, setInputValue] = useState(initialQuery);
  const [query, setQuery] = useState(initialQuery);
  const [result, setResult] = useState<FacilityListResponse | null>(initialResult);
  const [error, setError] = useState<string | null>(initialError);
  const [isSearching, setIsSearching] = useState(false);
  // The active filters are fixed for the life of this page render; a filter
  // submit navigates and mounts a new provider with the new parameters.
  const [params] = useState(filterParams);

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const controllerRef = useRef<AbortController | null>(null);
  const committedRef = useRef(initialQuery);
  const inFlightRef = useRef<string | null>(null);

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const runSearch = useCallback(
    (value: string) => {
      const next = value.trim();
      if (next === committedRef.current) {
        // Returning to the committed query cancels a slower search in flight.
        controllerRef.current?.abort();
        controllerRef.current = null;
        inFlightRef.current = null;
        setError(null);
        setIsSearching(false);
        return;
      }
      if (next === inFlightRef.current) return;

      clearTimer();
      controllerRef.current?.abort();
      const controller = new AbortController();
      controllerRef.current = controller;
      inFlightRef.current = next;
      setError(null);
      setIsSearching(true);

      listFacilities(
        { ...params, q: next || undefined, limit: 20 },
        { signal: controller.signal },
      )
        .then((data) => {
          if (controller.signal.aborted) return;
          setResult(data);
          setError(null);
          committedRef.current = next;
          setQuery(next);
          // Keep the URL shareable without asking Next.js to navigate.
          window.history.replaceState(
            null,
            "",
            `/directory${queryString({ ...params, q: next || undefined })}`,
          );
        })
        .catch((caught: unknown) => {
          if (controller.signal.aborted) return;
          setError(
            caught instanceof Error ? caught.message : "The search could not be completed.",
          );
        })
        .finally(() => {
          if (controllerRef.current !== controller) return;
          inFlightRef.current = null;
          setIsSearching(false);
        });
    },
    [clearTimer, params],
  );

  const setInput = useCallback(
    (value: string) => {
      setInputValue(value);
      clearTimer();
      timerRef.current = setTimeout(() => {
        timerRef.current = null;
        runSearch(value);
      }, SEARCH_DEBOUNCE_MS);
    },
    [clearTimer, runSearch],
  );

  const submit = useCallback(() => {
    clearTimer();
    runSearch(input);
  }, [clearTimer, input, runSearch]);

  useEffect(
    () => () => {
      clearTimer();
      controllerRef.current?.abort();
    },
    [clearTimer],
  );

  return (
    <DirectorySearchContext.Provider
      value={{ query, input, result, error, isSearching, setInput, submit }}
    >
      {children}
    </DirectorySearchContext.Provider>
  );
}

export function DirectorySearchInput({
  id,
  name = "q",
  placeholder,
}: {
  id: string;
  name?: string;
  placeholder?: string;
}) {
  const { input, setInput, submit } = useDirectorySearch();
  return (
    <Input
      id={id}
      name={name}
      type="search"
      value={input}
      placeholder={placeholder}
      autoComplete="off"
      onChange={(event) => setInput(event.target.value)}
      onKeyDown={(event) => {
        // Enter is an immediate search, not a full form submission.
        if (event.key === "Enter") {
          event.preventDefault();
          submit();
        }
      }}
    />
  );
}

export function DirectorySearchBar() {
  const { input, setInput, submit } = useDirectorySearch();
  return (
    <form
      role="search"
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
      className="border border-[#d1d8e6] bg-white p-3 shadow-[6px_6px_0_0_#fcd116]"
    >
      <label htmlFor="site-search" className="sr-only">
        Search facilities by name, address, or source identifier
      </label>
      <div className="flex flex-col gap-2 sm:flex-row">
        <Input
          id="site-search"
          name="q"
          type="search"
          value={input}
          placeholder="Search facility, municipality, or source ID"
          className="h-10"
          autoComplete="off"
          onChange={(event) => setInput(event.target.value)}
        />
        <Button type="submit" variant="blue" className="h-12 shrink-0 px-5">
          <Search aria-hidden="true" />
          Search
        </Button>
      </div>
    </form>
  );
}
