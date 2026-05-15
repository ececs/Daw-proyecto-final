import type { Meta, StoryObj } from '@storybook/nextjs-vite';
import { fn } from 'storybook/test';
import { KanbanBoard } from './KanbanBoard';
import { Ticket } from '@/types';

const meta: Meta<typeof KanbanBoard> = {
  title: 'Board/KanbanBoard',
  component: KanbanBoard,
  tags: ['autodocs', 'ai-generated'],
  parameters: {
    layout: 'fullscreen',
    nextjs: {
      appDirectory: true,
    },
  },
  decorators: [
    (Story) => (
      <div className="p-6 bg-slate-50 min-h-screen">
        <div className="max-w-7xl mx-auto">
          <Story />
        </div>
      </div>
    ),
  ],
};

export default meta;
type Story = StoryObj<typeof KanbanBoard>;

const mockTickets: Ticket[] = [
  {
    id: 't1',
    ticket_number: 101,
    title: 'Deploy latest stable release to Kubernetes node fleet',
    status: 'open',
    priority: 'critical',
    author_id: 'u1',
    assignee_id: null,
    assignee: null,
    author: null,
    client_url: null,
    client_summary: null,
    created_at: '2026-05-15T08:00:00Z',
    updated_at: '2026-05-15T08:00:00Z',
    description: null,
  },
  {
    id: 't2',
    ticket_number: 102,
    title: 'Investigate latency spikes in the Stripe webhook controller',
    status: 'in_progress',
    priority: 'high',
    author_id: 'u1',
    assignee_id: 'u2',
    assignee: {
      id: 'u2',
      name: 'Bob Developer',
      email: 'bob@example.com',
      avatar_url: 'https://api.dicebear.com/7.x/bottts/svg?seed=bob',
      created_at: '2026-01-01T00:00:00Z',
    },
    author: null,
    client_url: null,
    client_summary: null,
    created_at: '2026-05-15T09:30:00Z',
    updated_at: '2026-05-15T09:30:00Z',
    description: null,
  },
  {
    id: 't3',
    ticket_number: 103,
    title: 'Write documentation outline for API version 2.5 endpoints',
    status: 'in_review',
    priority: 'medium',
    author_id: 'u1',
    assignee_id: null,
    assignee: null,
    author: null,
    client_url: null,
    client_summary: null,
    created_at: '2026-05-15T10:00:00Z',
    updated_at: '2026-05-15T10:00:00Z',
    description: null,
  },
  {
    id: 't4',
    ticket_number: 104,
    title: 'Update user avatar component logic to handle SVGs cleanly',
    status: 'closed',
    priority: 'low',
    author_id: 'u1',
    assignee_id: 'u2',
    assignee: {
      id: 'u2',
      name: 'Bob Developer',
      email: 'bob@example.com',
      avatar_url: 'https://api.dicebear.com/7.x/bottts/svg?seed=bob',
      created_at: '2026-01-01T00:00:00Z',
    },
    author: null,
    client_url: null,
    client_summary: null,
    created_at: '2026-05-14T15:00:00Z',
    updated_at: '2026-05-14T18:00:00Z',
    description: null,
  },
];

export const FullBoard: Story = {
  args: {
    tickets: mockTickets,
    onStatusChange: fn(),
  },
};

export const EmptyBoard: Story = {
  args: {
    tickets: [],
    onStatusChange: fn(),
  },
};
