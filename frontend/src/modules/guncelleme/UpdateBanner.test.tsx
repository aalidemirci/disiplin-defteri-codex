import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SnackbarProvider } from "../../ui/SnackbarProvider";
import UpdateBanner from "./UpdateBanner";

const mocks = vi.hoisted(() => ({
  check: vi.fn(),
  downloadInstaller: vi.fn(),
  saveBlob: vi.fn(),
}));

vi.mock("./api", () => ({
  updateApi: {
    check: mocks.check,
    downloadInstaller: mocks.downloadInstaller,
  },
}));

vi.mock("../../lib/download", () => ({
  saveBlob: mocks.saveBlob,
}));

const STATUS = {
  current_version: "2026.7.0",
  latest_version: "2026.8.0",
  update_available: true,
  release_name: "Ağustos sürümü",
  published_at: "2026-08-01T12:00:00Z",
  release_url: "https://github.com/aalidemirci/disiplin-defteri-codex/releases/tag/v2026.8.0",
  can_download: true,
  installer_name: "disiplin-defteri-2026.8.0-win64-setup.exe",
  installer_size: 42,
};

function renderBanner() {
  return render(
    <SnackbarProvider>
      <UpdateBanner />
    </SnackbarProvider>,
  );
}

describe("UpdateBanner", () => {
  afterEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
  });

  it("yeni sürümü otomatik denetler ve doğrulanmış kurucuyu indirir", async () => {
    const blob = new Blob(["kurucu"]);
    mocks.check.mockResolvedValue(STATUS);
    mocks.downloadInstaller.mockResolvedValue(blob);
    const user = userEvent.setup();

    renderBanner();

    expect(await screen.findByText(/Disiplin Defteri 2026.8.0 hazır/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /güncellemeyi indir/i }));

    await waitFor(() => expect(mocks.downloadInstaller).toHaveBeenCalledTimes(1));
    expect(mocks.saveBlob).toHaveBeenCalledWith(blob, STATUS.installer_name);
  });

  it("kullanıcının ertelediği sürümü yeniden göstermez", async () => {
    window.localStorage.setItem("disiplin-defteri-dismissed-update", STATUS.latest_version);
    mocks.check.mockResolvedValue(STATUS);

    renderBanner();

    await waitFor(() => expect(mocks.check).toHaveBeenCalledTimes(1));
    expect(screen.queryByText(/Disiplin Defteri 2026.8.0 hazır/)).not.toBeInTheDocument();
  });
});
