/**
 * Selection store (Zustand).
 *
 * Tracks which tickets the user has multi-selected in the table /
 * kanban so other parts of the UI (toolbar bulk actions, AI sidebar
 * context) can react. Holds only the ids; the full ticket objects
 * stay in the data hooks.
 */

import { create } from 'zustand';

interface SelectionState {
  selectedTicketIds: string[];
  /** Add `id` to the selection if absent, remove it otherwise. */
  toggleTicket: (id: string) => void;
  /** Replace the current selection wholesale. */
  setSelection: (ids: string[]) => void;
  /** Empty the selection. */
  clearSelection: () => void;
}

export const useSelectionStore = create<SelectionState>((set) => ({
  selectedTicketIds: [],

  toggleTicket: (id) => set((state) => ({
    selectedTicketIds: state.selectedTicketIds.includes(id)
      ? state.selectedTicketIds.filter((tId) => tId !== id)
      : [...state.selectedTicketIds, id]
  })),

  setSelection: (ids) => set({ selectedTicketIds: ids }),

  clearSelection: () => set({ selectedTicketIds: [] }),
}));
