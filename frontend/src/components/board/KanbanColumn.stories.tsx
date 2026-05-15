import type { Meta, StoryObj } from '@storybook/nextjs-vite';
import { DndContext } from '@dnd-kit/core';
import { KanbanColumn } from './KanbanColumn';
import { Ticket } from '@/types';

const meta: Meta<typeof KanbanColumn> = {
  title: 'Board/KanbanColumn',
  component: KanbanColumn,
  tags: ['autodocs', 'ai-generated'],
  parameters: {
    nextjs: {
      appDirectory: true,
    },
  },
  decorators: [
    (Story) => (
      <DndContext>
        <div className="w-[360px] h-[600px] p-4">
          <Story />
        </div>
      </DndContext>
    ),
  ],
};

export default meta;
type Story = StoryObj<typeof KanbanColumn>;

const mockTickets: Ticket[] = [
  {
    id: 't1',
    ticket_number: 101,
    title: 'Deploy latest stable artifact to kubernetes production node cluster',
    status: 'open',
    priority: 'high',
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
    title: 'Clean up legacy CSS files and dead asset links',
    status: 'open',
    priority: 'low',
    author_id: 'u1',
    assignee_id: 'u2',
    assignee: {
      id: 'u2',
      name: 'Alice Developer',
      email: 'alice@example.com',
      avatar_url: 'https://api.dicebear.com/7.x/bottts/svg?seed=alice',
      created_at: '2026-01-01T00:00:00Z',
    },
    author: null,
    client_url: null,
    client_summary: null,
    created_at: '2026-05-15T09:30:00Z',
    updated_at: '2026-05-15T09:30:00Z',
    description: null,
  },
];

export const OpenColumn: Story = {
  args: {
    status: 'open',
    tickets: mockTickets,
  },
};

export const InProgressColumn: Story = {
  args: {
    status: 'in_progress',
    tickets: [
      {
        ...mockTickets[0],
        id: 't3',
        title: 'Resolve race condition in WebSocket auth channel handshake',
        status: 'in_progress',
        priority: 'critical',
      },
    ],
  },
};

export const EmptyColumn: Story = {
  args: {
    status: 'closed',
    tickets: [],
  },
};
