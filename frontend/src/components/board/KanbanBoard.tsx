/**
 * `KanbanBoard` — drag-and-drop ticket board powered by `dnd-kit`.
 *
 * Layout:
 *
 * ```
 *   <DndContext>                  // drag state for all descendants
 *     <KanbanColumn /> × 4        // useDroppable, one per status
 *       <KanbanCard />  × n       // useDraggable
 *     <DragOverlay />             // floating preview while dragging
 *   </DndContext>
 * ```
 *
 * Drag lifecycle:
 *
 *  1. `onDragStart` stores the active ticket so the overlay can
 *     render a faithful copy at the cursor.
 *  2. `onDragEnd` reads the drop target id (matches `TicketStatus`),
 *     ignores no-op drops, and delegates to `onStatusChange` which
 *     in turn applies the optimistic update + PATCH.
 *
 * **Sensors:** a 5 px activation distance for the mouse and a 250 ms
 * delay for touch prevent accidental drags during a normal tap.
 */

"use client";

import {
  DndContext,
  DragEndEvent,
  DragOverlay,
  DragStartEvent,
  MouseSensor,
  TouchSensor,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import { useState } from "react";
import { Ticket, TicketStatus } from "@/types";
import { KanbanColumn } from "./KanbanColumn";
import { KanbanCard } from "./KanbanCard";
import { useToast } from "@/hooks/use-toast";

const STATUSES: TicketStatus[] = ["open", "in_progress", "in_review", "closed"];

interface KanbanBoardProps {
  tickets: Ticket[];
  onStatusChange: (ticketId: string, newStatus: TicketStatus) => Promise<void>;
}

export function KanbanBoard({ tickets, onStatusChange }: KanbanBoardProps) {
  const [activeTicket, setActiveTicket] = useState<Ticket | null>(null);
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const { toast } = useToast();

  // Why: 5 px distance / 250 ms touch delay so taps are not
  // misinterpreted as drag starts on the card body.
  const sensors = useSensors(
    useSensor(MouseSensor, { activationConstraint: { distance: 5 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 250, tolerance: 5 } })
  );

  const handleDragStart = (event: DragStartEvent) => {
    setActiveTicket(event.active.data.current?.ticket ?? null);
  };

  const handleDragEnd = async (event: DragEndEvent) => {
    setActiveTicket(null);

    const { active, over } = event;
    if (!over) return;

    const ticketId = active.id as string;
    const newStatus = over.id as TicketStatus;
    const currentStatus = (active.data.current?.ticket as Ticket)?.status;

    if (newStatus === currentStatus || !STATUSES.includes(newStatus)) return;

    setUpdatingId(ticketId);
    try {
      await onStatusChange(ticketId, newStatus);
    } catch {
      toast({
        title: "Status change failed",
        description: "Could not move the ticket. Please try again.",
        variant: "destructive",
      });
    } finally {
      setUpdatingId(null);
    }
  };

  // Why: pre-group by status so each column receives a stable slice
  // and React can keep its key-based reconciliation cheap.
  const ticketsByStatus = STATUSES.reduce<Record<TicketStatus, Ticket[]>>(
    (acc, status) => {
      acc[status] = tickets.filter((t) => t.status === status);
      return acc;
    },
    { open: [], in_progress: [], in_review: [], closed: [] }
  );

  return (
    <DndContext sensors={sensors} onDragStart={handleDragStart} onDragEnd={handleDragEnd}>
      <div className="flex gap-4 overflow-x-auto pb-4">
        {STATUSES.map((status) => (
          <div key={status} className="min-w-[260px] flex-1">
            <KanbanColumn status={status} tickets={ticketsByStatus[status]} updatingId={updatingId} />
          </div>
        ))}
      </div>

      {/* Why: `DragOverlay` floats above the column DOM so the moving
          card never gets clipped by overflow on its origin column. */}
      <DragOverlay>
        {activeTicket && (
          <div className="rotate-1 shadow-xl">
            <KanbanCard ticket={activeTicket} />
          </div>
        )}
      </DragOverlay>
    </DndContext>
  );
}
