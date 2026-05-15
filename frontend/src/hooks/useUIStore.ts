/**
 * Transient UI store (Zustand).
 *
 * Holds non-persistent flags that drive layout chrome — currently
 * only the AI chat sidebar visibility. Lives in its own store so
 * unrelated components do not re-render when, say, a notification is
 * marked as read.
 */

import { create } from "zustand";

interface UIState {
  isChatOpen: boolean;
  setChatOpen: (open: boolean) => void;
  toggleChat: () => void;
}

export const useUIStore = create<UIState>((set) => ({
  isChatOpen: false,
  setChatOpen: (open) => set({ isChatOpen: open }),
  toggleChat: () => set((state) => ({ isChatOpen: !state.isChatOpen })),
}));
