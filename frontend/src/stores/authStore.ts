/**
 * Authentication store (Zustand).
 *
 * Holds the currently authenticated `User` and a loading flag that
 * is `true` while the initial `/auth/me` request is in flight. The
 * store is hydrated once during app startup (`AuthInitializer`), so
 * downstream components can read `user` synchronously without
 * triggering additional network calls.
 */

import { create } from "zustand";
import { User } from "@/types";
import api from "@/lib/api";

interface AuthState {
  user: User | null;
  isLoading: boolean;
  /** Resolve the current user from the backend session cookie / JWT. */
  fetchUser: () => Promise<void>;
  /** Wipe the cached user (used on logout). */
  clearUser: () => void;
}

const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isLoading: true,

  fetchUser: async () => {
    try {
      const { data } = await api.get<User>("/auth/me");
      set({ user: data, isLoading: false });
    } catch {
      // Why: a 401 or network error simply means "not authenticated";
      // we surface that as `user = null` instead of propagating the error.
      set({ user: null, isLoading: false });
    }
  },

  clearUser: () => set({ user: null }),
}));

export default useAuthStore;
