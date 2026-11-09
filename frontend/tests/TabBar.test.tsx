import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

let pathname = "/";
vi.mock("next/navigation", () => ({ usePathname: () => pathname }));

import { TabBar, isActive } from "@/components/TabBar";

describe("isActive", () => {
  it("matches Today only at the root", () => {
    expect(isActive("/", "/")).toBe(true);
    expect(isActive("/", "/research")).toBe(false);
  });
  it("matches nested research routes", () => {
    expect(isActive("/research", "/research/PERSISTENT")).toBe(true);
    expect(isActive("/research", "/researcher")).toBe(false);
  });
});

describe("TabBar", () => {
  it("marks the current route", () => {
    pathname = "/research/DIXON";
    render(<TabBar />);
    expect(screen.getByRole("link", { name: /research/i })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: /today/i })).not.toHaveAttribute("aria-current");
  });
});
