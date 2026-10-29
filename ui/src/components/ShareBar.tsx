/*
  Sharing one verdict: its link (/s/<id>) and its card as an image.

  On a phone (and anywhere the browser offers it) both go through the system share sheet, so
  the visitor picks the app. Elsewhere the link is copied and the image is downloaded. Nothing is
  sent anywhere by this page: the share sheet and the clipboard belong to the visitor's device.
*/
import { useEffect, useState } from "react";
import { Image as ImageIcon, Link2 } from "lucide-react";
import { ControlButton } from "@/components/Debate";
import type { GallerySession } from "@/lib/gallery";
import { sessionUrl } from "@/lib/route";

function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

export function ShareBar({ session }: { session: GallerySession }) {
  const [status, setStatus] = useState("");
  const [drawing, setDrawing] = useState(false);
  const url = sessionUrl(session.id);
  const text =
    session.kind === "council" && session.verdict_label
      ? `The council's verdict on ${session.item}: ${session.verdict_label}.`
      : `${session.item}: the council declined it, since it is not a gadget.`;
  const canShare = typeof navigator !== "undefined" && typeof navigator.share === "function";

  // A status line clears itself, so an old "Link copied." never sits next to a new session.
  useEffect(() => {
    if (!status) return;
    const timer = setTimeout(() => setStatus(""), 4000);
    return () => clearTimeout(timer);
  }, [status]);

  const shareLink = async () => {
    if (canShare) {
      try {
        await navigator.share({ title: "Talk Me Out of It", text, url });
        return;
      } catch (error) {
        if (isAbort(error)) return;
      }
    }
    try {
      await navigator.clipboard.writeText(url);
      setStatus("Link copied.");
    } catch {
      setStatus(`Copy this link: ${url}`);
    }
  };

  const shareImage = async () => {
    setDrawing(true);
    setStatus("Drawing the card…");
    try {
      // The drawing code is fetched the first time someone asks for an image, like Under the hood.
      const { drawShareCard } = await import("@/lib/share-card");
      const blob = await drawShareCard(session);
      const file = new File([blob], `talk-me-out-of-it-${session.id}.png`, { type: "image/png" });
      if (canShare && navigator.canShare?.({ files: [file] })) {
        setStatus("");
        await navigator.share({ files: [file], title: "Talk Me Out of It", text });
        return;
      }
      const href = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = href;
      a.download = file.name;
      a.click();
      setTimeout(() => URL.revokeObjectURL(href), 10_000);
      setStatus("Image saved.");
    } catch (error) {
      setStatus(isAbort(error) ? "" : "The image could not be made in this browser.");
    } finally {
      setDrawing(false);
    }
  };

  return (
    <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2">
      <div className="flex items-center gap-2">
        <ControlButton icon={Link2} onClick={shareLink}>
          {canShare ? "Share link" : "Copy link"}
        </ControlButton>
        <ControlButton icon={ImageIcon} onClick={shareImage} disabled={drawing}>
          {canShare ? "Share image" : "Save image"}
        </ControlButton>
      </div>
      <p role="status" aria-live="polite" className="min-w-0 break-all font-mono text-[11px] text-muted-foreground">
        {status}
      </p>
    </div>
  );
}
