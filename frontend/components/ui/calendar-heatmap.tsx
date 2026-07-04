"use client"

import * as React from "react"
import { cn } from "@/lib/utils"

export type ActivityData = {
  date: string // YYYY-MM-DD format
  count: number
}

export type ActivityHeatmapProps = {
  data: ActivityData[]
  className?: string
}

// Color levels for the heatmap (0 = no activity, 4 = max activity).
// Uses the palette's chart ramp so intensity follows the active theme.
const COLORS = [
  "bg-surface2", // 0 - no activity
  "bg-chart-1/60", // 1 - low
  "bg-chart-2/75", // 2 - medium-low
  "bg-chart-3/90", // 3 - medium-high
  "bg-chart-4", // 4 - high
]

const DAY_LABELS = ["", "Mon", "", "Wed", "", "Fri", ""]

// Cell size + gap
const CELL_SIZE = 11
const GAP = 3
const WEEK_WIDTH = CELL_SIZE + GAP // 14px per week column
const LEFT_PADDING = 32 // Space for day labels

function getColorLevel(count: number, maxCount: number): number {
  if (count === 0) return 0
  if (maxCount === 0) return 0
  const ratio = count / maxCount
  if (ratio <= 0.25) return 1
  if (ratio <= 0.5) return 2
  if (ratio <= 0.75) return 3
  return 4
}

function formatDate(date: Date): string {
  return date.toISOString().split("T")[0]
}

function getMonthLabel(date: Date): string {
  return date.toLocaleDateString("en-US", { month: "short" })
}

function ActivityHeatmap({ data, className }: ActivityHeatmapProps) {
  const containerRef = React.useRef<HTMLDivElement>(null)
  const [weeks, setWeeks] = React.useState<number | null>(null) // null = not yet calculated

  // Calculate weeks based on container width using ResizeObserver
  React.useEffect(() => {
    if (!containerRef.current) return

    const updateWeeks = (width: number) => {
      const availableWidth = width - LEFT_PADDING - 10 // 10px buffer
      const calculatedWeeks = Math.floor(availableWidth / WEEK_WIDTH)
      setWeeks(Math.max(calculatedWeeks, 8)) // Minimum 8 weeks
    }

    // Initial calculation
    updateWeeks(containerRef.current.offsetWidth)

    // Use ResizeObserver for responsive updates
    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        updateWeeks(entry.contentRect.width)
      }
    })

    resizeObserver.observe(containerRef.current)
    return () => resizeObserver.disconnect()
  }, [])

  // Build a map of date -> count
  const countMap = React.useMemo(() => {
    const map = new Map<string, number>()
    data.forEach((item) => {
      map.set(item.date, item.count)
    })
    return map
  }, [data])

  // Find max count for color scaling
  const maxCount = React.useMemo(() => {
    return Math.max(...data.map((d) => d.count), 1)
  }, [data])

  // Generate the grid data (weeks x 7 days)
  const gridData = React.useMemo(() => {
    if (weeks === null) return []

    const today = new Date()
    const grid: { date: Date; count: number; dateStr: string }[][] = []

    // Start from the beginning of the week, `weeks` weeks ago
    const startDate = new Date(today)
    startDate.setDate(startDate.getDate() - (weeks * 7) + (7 - today.getDay()))

    for (let week = 0; week < weeks; week++) {
      const weekData: { date: Date; count: number; dateStr: string }[] = []
      for (let day = 0; day < 7; day++) {
        const date = new Date(startDate)
        date.setDate(startDate.getDate() + week * 7 + day)
        const dateStr = formatDate(date)
        const count = countMap.get(dateStr) || 0
        weekData.push({ date, count, dateStr })
      }
      grid.push(weekData)
    }
    return grid
  }, [countMap, weeks])

  // Get month labels with their positions
  const monthLabels = React.useMemo(() => {
    const labels: { label: string; weekIndex: number }[] = []
    let lastMonth = -1

    gridData.forEach((week, weekIndex) => {
      // Check the first day of each week
      const firstDay = week[0]
      const month = firstDay.date.getMonth()
      if (month !== lastMonth) {
        labels.push({ label: getMonthLabel(firstDay.date), weekIndex })
        lastMonth = month
      }
    })

    // Skip the first month label if it only has 1 week of data
    // This prevents "Aug" and "Sept" from being smooshed together on mobile
    // when the chart starts in late August with just a few days
    if (labels.length >= 2 && labels[1].weekIndex <= 1) {
      return labels.slice(1)
    }

    return labels
  }, [gridData])

  const [tooltip, setTooltip] = React.useState<{
    x: number
    y: number
    date: string
    count: number
  } | null>(null)

  // Show skeleton while calculating width
  if (weeks === null) {
    return (
      <div ref={containerRef} className={cn("relative w-full", className)}>
        <div className="h-[120px] w-full animate-pulse rounded bg-surface2/30" />
      </div>
    )
  }

  return (
    <div ref={containerRef} className={cn("relative w-full", className)}>
      {/* Month labels */}
      <div className="relative h-4 mb-1" style={{ marginLeft: `${LEFT_PADDING}px` }}>
        {monthLabels.map((item, i) => (
          <div
            key={i}
            className="absolute text-xs text-faint"
            style={{ left: `${item.weekIndex * WEEK_WIDTH}px` }}
          >
            {item.label}
          </div>
        ))}
      </div>

      <div className="flex">
        {/* Day labels */}
        <div className="flex flex-col gap-[3px] mr-2 text-xs text-faint" style={{ width: `${LEFT_PADDING - 8}px` }}>
          {DAY_LABELS.map((label, i) => (
            <div key={i} className="h-[11px] leading-[11px] text-right pr-1">
              {label}
            </div>
          ))}
        </div>

        {/* Grid */}
        <div className="flex gap-[3px] flex-1">
          {gridData.map((week, weekIndex) => (
            <div key={weekIndex} className="flex flex-col gap-[3px]">
              {week.map((day, dayIndex) => {
                const colorLevel = getColorLevel(day.count, maxCount)
                const isFuture = day.date > new Date()

                return (
                  <div
                    key={dayIndex}
                    className={cn(
                      "w-[11px] h-[11px] rounded-sm transition-colors cursor-pointer",
                      isFuture ? "bg-card/30" : COLORS[colorLevel],
                      !isFuture && "hover:ring-1 hover:ring-border-strong"
                    )}
                    onMouseEnter={(e) => {
                      if (!isFuture) {
                        const rect = e.currentTarget.getBoundingClientRect()
                        setTooltip({
                          x: rect.left + rect.width / 2,
                          y: rect.top,
                          date: day.date.toLocaleDateString("en-US", {
                            weekday: "short",
                            month: "short",
                            day: "numeric",
                          }),
                          count: day.count,
                        })
                      }
                    }}
                    onMouseLeave={() => setTooltip(null)}
                  />
                )
              })}
            </div>
          ))}
        </div>
      </div>

      {/* Tooltip */}
      {tooltip && (
        <div
          className="fixed z-50 px-2 py-1 text-xs bg-background border border-border rounded shadow-lg pointer-events-none"
          style={{
            left: tooltip.x,
            top: tooltip.y - 32,
            transform: "translateX(-50%)",
          }}
        >
          <span className="font-medium text-foreground">
            {tooltip.count} {tooltip.count === 1 ? "message" : "messages"}
          </span>
          <span className="text-muted-foreground"> on {tooltip.date}</span>
        </div>
      )}

      {/* Legend */}
      <div className="flex items-center justify-end gap-1 mt-2 text-xs text-faint">
        <span>Less</span>
        {COLORS.map((color, i) => (
          <div key={i} className={cn("w-[11px] h-[11px] rounded-sm", color)} />
        ))}
        <span>More</span>
      </div>
    </div>
  )
}

ActivityHeatmap.displayName = "ActivityHeatmap"

export { ActivityHeatmap }

