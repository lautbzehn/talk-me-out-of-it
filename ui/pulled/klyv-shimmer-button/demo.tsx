import { ArrowRight, Sparkles } from "lucide-react";
import { ShimmerButton } from "@/components/ui/klyv-shimmer-button";

const SourceExample = () => (
          <div className="flex w-full flex-wrap items-center gap-3">
            <ShimmerButton size="lg">
              <Sparkles size={16} strokeWidth={2.5} aria-hidden="true" />
              Upgrade to Plus
            </ShimmerButton>
            <ShimmerButton tone="ink">
              Send money
              <ArrowRight size={15} strokeWidth={2.5} aria-hidden="true" />
            </ShimmerButton>
            <ShimmerButton tone="glass" onHover>
              Sweeps on hover
            </ShimmerButton>
            <ShimmerButton size="sm" tone="glass" glow={false}>
              No glow
            </ShimmerButton>
          </div>
        );


export default function Demo(){return <div data-component-demo className="flex min-h-screen w-full items-center justify-center bg-canvas p-8 text-ink"><div className="w-full max-w-[620px]"><SourceExample /></div></div>}
