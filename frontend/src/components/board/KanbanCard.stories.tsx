import type { Meta, StoryObj } from '@storybook/nextjs-vite';
import { DndContext } from '@dnd-kit/core';
import { KanbanCard } from './KanbanCard';
import { Ticket } from '@/types';

/**
 * The KanbanCard represents an individual task tile in the project board view.
 * It incorporates drag-and-drop support via `dnd-kit` and uses visual color codes
 * to immediately signify ticket priority and assignment status.
 */
const meta: Meta<typeof KanbanCard> = {
  title: 'Board/KanbanCard',
  component: KanbanCard,
  tags: ['autodocs', 'ai-generated'],
  parameters: {
    nextjs: {
      appDirectory: true,
    },
  },
  decorators: [
    (Story) => (
      // dnd-kit components MUST be wrapped inside DndContext to avoid runtime context errors
      <DndContext>
        <div className="w-[320px] p-4 bg-slate-50 rounded-xl">
          <Story />
        </div>
      </DndContext>
    ),
  ],
};

export default meta;
type Story = StoryObj<typeof KanbanCard>;

// Base template for building rich mocked tickets
const baseTicket: Ticket = {
  id: 'ticket-uuid-1',
  ticket_number: 104,
  title: 'Integrate Stripe Subscription Webhooks',
  description: 'Ensure local payment plans are synced in real time.',
  status: 'in_progress',
  priority: 'high',
  author_id: 'user-1',
  assignee_id: 'user-2',
  client_url: null,
  client_summary: null,
  created_at: '2026-05-15T10:00:00Z',
  updated_at: '2026-05-15T12:00:00Z',
  author: null,
  assignee: {
    id: 'user-2',
    name: 'Alice Developer',
    email: 'alice@example.com',
    avatar_url: 'https://api.dicebear.com/7.x/bottts/svg?seed=alice',
    created_at: '2026-01-01T00:00:00Z',
  },
};

/** Represents a standard, highly urgent ticket currently in the development cycle. */
export const HighPriority: Story = {
  args: {
    ticket: {
      ...baseTicket,
      priority: 'high',
      title: 'Resolve memory leak inside Websocket listening loop',
    },
  },
};

/** Represents a ticket requiring immediate operational resolution. */
export const CriticalPriority: Story = {
  args: {
    ticket: {
      ...baseTicket,
      priority: 'critical',
      title: 'PRODUCTION OUTAGE: Database CPU utilization spiking to 100%',
      ticket_number: 105,
    },
  },
};

/** Shows a standard ticket with low priority. */
export const LowPriority: Story = {
  args: {
    ticket: {
      ...baseTicket,
      priority: 'low',
      title: 'Minor UI alignment issue in footer link cluster',
      ticket_number: 99,
    },
  },
};

/** Simulates the visual overlay loading state when the ticket state updates over REST. */
export const UpdatingState: Story = {
  args: {
    ticket: baseTicket,
    isUpdating: true,
  },
};

/** Represents an orphaned ticket with no assigned technician yet. */
export const Unassigned: Story = {
  args: {
    ticket: {
      ...baseTicket,
      title: 'Process initial server setup and nginx config',
      assignee: null,
      assignee_id: null,
      ticket_number: 106,
    },
  },
};
