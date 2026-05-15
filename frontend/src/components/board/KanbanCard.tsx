"use client";

import { useDraggable } from "@dnd-kit/core";
import { CSS } from "@dnd-kit/utilities";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { Ticket } from "@/types";
import { UserAvatar } from "@/components/ui/UserAvatar";
import { PRIORITY_CONFIG } from "@/lib/utils";

interface KanbanCardProps {
  /** The single ticket data model to present visual metadata and handle DnD actions. */
  ticket: Ticket;
  /** Disables dragging operations and presents a spinner overlays while updating API state. */
  isUpdating?: boolean;
}

/**
 * `KanbanCard` — draggable ticket tile in the Kanban view.
 *
 * Wraps `dnd-kit`'s `useDraggable`. The card fades to 40 % opacity
 * while being dragged; the full-quality preview is rendered by
 * `KanbanBoard` as a `DragOverlay`.
 */
export function KanbanCard({ ticket, isUpdating = false }: KanbanCardProps) {
  const router = useRouter();

  // Why: attach the full ticket on `data` so `KanbanBoard.onDragEnd`
  // can reuse it without an extra `find` against the cached list.
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: ticket.id,
    data: { ticket },
    disabled: isUpdating,
  });

  const style = {
    transform: CSS.Translate.toString(transform),
    opacity: isDragging ? 0.4 : 1,
  };

  const priorityCfg = PRIORITY_CONFIG[ticket.priority];

  const handleClick = () => {
    if (!isDragging) {
      router.push(`/tickets/${ticket.ticket_number}`);
    }
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      onClick={handleClick}
      className={`relative bg-white rounded-lg border p-3 shadow-sm transition-all group ${
        isUpdating
          ? "border-blue-300 opacity-60 cursor-not-allowed"
          : "border-slate-200 cursor-grab active:cursor-grabbing hover:border-slate-300 hover:shadow-md"
      }`}
    >
      {isUpdating && (
        <div className="absolute inset-0 flex items-center justify-center rounded-lg bg-white/60 z-10">
          <Loader2 className="w-4 h-4 animate-spin text-blue-500" />
        </div>
      )}
      <div className="flex items-start justify-between gap-2 mb-2">
        <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${priorityCfg.color}`}>
          {priorityCfg.label}
        </span>
        <span className="text-xs text-slate-400 font-mono shrink-0">
          #{ticket.ticket_number}
        </span>
      </div>

      <p className="text-sm font-medium text-slate-800 leading-snug mb-3 group-hover:text-blue-600 transition-colors line-clamp-2">
        {ticket.title}
      </p>

      {ticket.assignee && (
        <div className="flex items-center gap-1.5">
          <UserAvatar 
            src={ticket.assignee.avatar_url} 
            name={ticket.assignee.name} 
            size="xs" 
          />
          <span className="text-xs text-slate-500 truncate">{ticket.assignee.name}</span>
        </div>
      )}
    </div>
  );
}
