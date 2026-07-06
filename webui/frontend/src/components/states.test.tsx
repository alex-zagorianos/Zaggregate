import { describe, it, expect, vi } from "vitest";
import { isValidElement, type ReactElement } from "react";

import { queryGuardDecision, type QueryGuardLike } from "./states";
import { ApiError } from "@/api/client";
import { LoadingState, ErrorState } from "./states";

/* queryGuardDecision is the pure decision logic behind useQueryGuard (the
 * hooks/render wrapper can't be unit-tested without React Testing Library,
 * which this project doesn't have — see
 * brain/techdebt-register-2026-07-05.md #21). These tests pin the four
 * branches: loading, ApiError, non-ApiError error, and ready (null). */

function fakeQuery(overrides: Partial<QueryGuardLike> = {}): QueryGuardLike {
  return {
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    ...overrides,
  };
}

describe("queryGuardDecision", () => {
  it("returns the default LoadingState while loading", () => {
    const result = queryGuardDecision(fakeQuery({ isLoading: true }), {
      fallback: "fallback text",
    });
    expect(isValidElement(result)).toBe(true);
    expect((result as ReactElement).type).toBe(LoadingState);
  });

  it("returns a custom loading element when one is supplied", () => {
    const custom = <p>custom loading</p>;
    const result = queryGuardDecision(fakeQuery({ isLoading: true }), {
      fallback: "fallback text",
      loading: custom,
    });
    expect(result).toBe(custom);
  });

  it("prioritizes isLoading over isError (loading always wins)", () => {
    const result = queryGuardDecision(
      fakeQuery({ isLoading: true, isError: true }),
      { fallback: "fallback text" },
    );
    expect((result as ReactElement).type).toBe(LoadingState);
  });

  it("surfaces an ApiError's own message on error", () => {
    const error = new ApiError("The server said no.", 500, null);
    const result = queryGuardDecision(fakeQuery({ isError: true, error }), {
      title: "Couldn't load your board",
      fallback: "The board service didn't respond.",
    });
    expect(isValidElement(result)).toBe(true);
    const el = result as ReactElement<{
      title?: string;
      message?: string;
      onRetry?: () => void;
      className?: string;
    }>;
    expect(el.type).toBe(ErrorState);
    expect(el.props.title).toBe("Couldn't load your board");
    expect(el.props.message).toBe("The server said no.");
  });

  it("falls back to the caller's message for a non-ApiError error", () => {
    const result = queryGuardDecision(
      fakeQuery({ isError: true, error: new Error("boom") }),
      { title: "Couldn't load your board", fallback: "The fallback text." },
    );
    const el = result as ReactElement<{ message?: string }>;
    expect(el.props.message).toBe("The fallback text.");
  });

  it("wires onRetry to the query's refetch", () => {
    const refetch = vi.fn();
    const result = queryGuardDecision(
      fakeQuery({ isError: true, error: new Error("boom"), refetch }),
      { fallback: "fallback text" },
    );
    const el = result as ReactElement<{ onRetry?: () => void }>;
    el.props.onRetry?.();
    expect(refetch).toHaveBeenCalledOnce();
  });

  it("passes errorClassName through to ErrorState", () => {
    const result = queryGuardDecision(
      fakeQuery({ isError: true, error: new Error("boom") }),
      { fallback: "fallback text", errorClassName: "min-h-0 py-8" },
    );
    const el = result as ReactElement<{ className?: string }>;
    expect(el.props.className).toBe("min-h-0 py-8");
  });

  it("returns null when the query is ready (neither loading nor error)", () => {
    const result = queryGuardDecision(fakeQuery(), { fallback: "fallback text" });
    expect(result).toBeNull();
  });
});
