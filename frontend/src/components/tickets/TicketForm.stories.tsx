import type { Meta, StoryObj } from '@storybook/react';
import { fn } from 'storybook/test';
import { TicketForm } from './TicketForm';
import { Ticket, User } from '@/types';

const meta: Meta<typeof TicketForm> = {
  title: 'Tickets/TicketForm',
  component: TicketForm,
  tags: ['autodocs', 'ai-generated'],
  parameters: {
    layout: 'centered',
  },
};

export default meta;
type Story = StoryObj<typeof TicketForm>;

const mockUsers: User[] = [
  {
    id: 'user-1',
    email: 'alice@example.com',
    name: 'Alice Dev',
    avatar_url: 'https://api.dicebear.com/7.x/bottts/svg?seed=alice',
    created_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 'user-2',
    email: 'bob@example.com',
    name: 'Bob Systems',
    avatar_url: 'https://api.dicebear.com/7.x/bottts/svg?seed=bob',
    created_at: '2026-01-01T00:00:00Z',
  },
];

const existingTicket: Ticket = {
  id: 't1',
  ticket_number: 101,
  title: 'Fix critical memory leak in WS server',
  status: 'in_progress',
  priority: 'high',
  description: 'The process consumes 100% RAM after 4 hours of continuous runtime.',
  author_id: 'user-1',
  assignee_id: 'user-2',
  assignee: mockUsers[1],
  author: null,
  client_url: 'https://bankops.internal.net',
  client_summary: 'Legacy Java middleware cluster experiencing OutOfMemoryError.',
  created_at: '2026-05-15T08:00:00Z',
  updated_at: '2026-05-15T08:00:00Z',
};

export const CreateTicket: Story = {
  args: {
    open: true,
    onClose: fn(),
    onSuccess: fn(),
    users: mockUsers,
  },
};

export const EditTicket: Story = {
  args: {
    open: true,
    onClose: fn(),
    onSuccess: fn(),
    users: mockUsers,
    ticket: existingTicket,
  },
};
