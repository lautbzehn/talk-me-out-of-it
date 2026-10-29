"use client";
import {ThemeProvider as LibraryDemoThemeProvider} from "next-themes";
import { ChartKpi } from "@/components/ui/tweenly-chart-kpi"

const data = [
  { date: "Jun 01", revenue: 4210, previous: 3890 },
  { date: "Jun 02", revenue: 3980, previous: 4020 },
  { date: "Jun 03", revenue: 4630, previous: 3710 },
  { date: "Jun 04", revenue: 4890, previous: 3950 },
  { date: "Jun 05", revenue: 4420, previous: 4180 },
  { date: "Jun 06", revenue: 3610, previous: 3320 },
  { date: "Jun 07", revenue: 3340, previous: 3050 },
  { date: "Jun 08", revenue: 4750, previous: 3980 },
  { date: "Jun 09", revenue: 5120, previous: 4110 },
  { date: "Jun 10", revenue: 5380, previous: 4270 },
  { date: "Jun 11", revenue: 4960, previous: 4390 },
  { date: "Jun 12", revenue: 5570, previous: 4210 },
  { date: "Jun 13", revenue: 4280, previous: 3760 },
  { date: "Jun 14", revenue: 5840, previous: 3940 },
]

export function Demo() {
  return (
    <ChartKpi
      data={data}
      goal={70000}
      sparkHeight={72}
      title="Revenue"
      description="Last 14 days"
      valueFormat="currency"
      index="date"
      valueKey="revenue"
      compareKey="previous"
    />
  )
}

function SourceSpecimen(){return <Demo/>}
export default function LibraryRegistryPreview(){return <LibraryDemoThemeProvider defaultTheme="dark" enableSystem={false}><div data-component-demo data-demo-theme="dark" data-theme="dark" className="dark" style={{background:"var(--background)",color:"var(--foreground)"}}><div className="relative w-full min-w-0 max-w-5xl min-h-[400px] flex items-center justify-center"><SourceSpecimen/></div></div></LibraryDemoThemeProvider>}
