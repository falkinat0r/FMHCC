import { formatCount } from "../../lib/format";
import { Button } from "../ui/button";
import { ChevronLeft, ChevronRight } from "lucide-react";

interface PaginationProps {
  page: number;
  totalPages: number;
  total: number;
  onChange: (page: number) => void;
}

/** Standard-Paging (frozen Paged-Envelope). */
export function Pagination({ page, totalPages, total, onChange }: PaginationProps) {
  if (totalPages <= 1 && total === 0) return null;
  return (
    <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
      <span>{formatCount(total)} gesamt</span>
      <div className="flex items-center gap-1">
        <Button
          variant="outline"
          size="sm"
          aria-label="Vorherige Seite"
          disabled={page <= 1}
          onClick={() => onChange(page - 1)}
        >
          <ChevronLeft className="h-4 w-4" aria-hidden="true" />
        </Button>
        <span className="px-2">
          Seite {page} / {totalPages}
        </span>
        <Button
          variant="outline"
          size="sm"
          aria-label="Naechste Seite"
          disabled={page >= totalPages}
          onClick={() => onChange(page + 1)}
        >
          <ChevronRight className="h-4 w-4" aria-hidden="true" />
        </Button>
      </div>
    </div>
  );
}
