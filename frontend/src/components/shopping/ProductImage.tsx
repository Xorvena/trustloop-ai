"use client";
import { ImageOff } from "lucide-react";
import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

interface Props { src: string | null; source?: string | null; name: string; className?: string }

/** Shows the product image; falls back to a neutral placeholder when there is no URL or the image fails to load.
 *  Generic catalog illustrations are tagged so they are never mistaken for real product photos. */
export function ProductImage({ src, source, name, className }: Props) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [src]);
  const showImage = Boolean(src) && !failed;
  const photo = source === "provider_photo" || source === "licensed_photo";
  return (
    // Fixed-size frame; the <img> is taken out of flow and fitted INSIDE it. (A grid with an auto row let the image render at its
    // natural height and `overflow-hidden` then showed only its top slice.) Photos get a light backdrop so transparent product shots stay visible.
    <div className={cn("relative flex items-center justify-center overflow-hidden rounded-xl", photo && showImage ? "bg-white" : "bg-gradient-to-br from-navy-700 to-navy-800", className)}>
      {showImage ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={src as string} alt={name} loading="lazy" onError={() => setFailed(true)} className="absolute inset-0 h-full w-full object-contain p-2" />
      ) : (
        <div role="img" aria-label="No image available" className="flex flex-col items-center gap-1 text-slate-500">
          <ImageOff className="h-7 w-7" /><span className="text-xs">No image available</span>
        </div>
      )}
      {showImage && source === "provider_photo" && (
        <span title="Photo supplied by the demo product provider (not a retailer listing)" className="absolute bottom-1.5 right-1.5 rounded bg-black/60 px-1.5 py-0.5 text-[10px] text-slate-200">Demo photo</span>
      )}
      {showImage && source === "illustration" && (
        <span title="Generic illustration, not a photo of this exact product" className="absolute bottom-1.5 right-1.5 rounded bg-black/50 px-1.5 py-0.5 text-[10px] text-slate-300">Illustration</span>
      )}
    </div>
  );
}
