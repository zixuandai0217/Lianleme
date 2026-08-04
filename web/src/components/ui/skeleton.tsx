/* Shared loading placeholder that follows the restrained surface geometry. */
import { cn } from "@/lib/utils"

function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="skeleton"
      className={cn("animate-pulse rounded-sm bg-muted", className)}
      {...props}
    />
  )
}

export { Skeleton }
