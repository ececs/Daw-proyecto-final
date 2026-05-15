import type { Meta, StoryObj } from '@storybook/react';
import { fn } from 'storybook/test';
import { TicketTable } from './TicketTable';
import { Ticket, TicketFilters, User } from '@/types';

const meta: Meta<typeof TicketTable> = {
  title: 'Tickets/TicketTable',
  component: TicketTable,
  tags: ['autodocs', 'ai-generated'],
  parameters: {
    layout: 'padded',
    nextjs: {
      appDirectory: true,
    },
  },
  argTypes: {
    isLoading: { control: 'boolean' },
    total: { control: 'number' },
  },
};

export default meta;
type Story = StoryObj<typeof TicketTable>;

const mockUser: User = {
  id: 'user-alice',
  email: 'alice@example.com',
  name: 'Alice Dev',
  avatar_url: 'https://api.dicebear.com/7.x/bottts/svg?seed=alice',
  created_at: '2026-01-01T00:00:00Z',
};

const mockTickets: Ticket[] = [
  {
    id: '1',
    ticket_number: 101,
    title: 'Database connection timeout during peak traffic hours',
    status: 'open',
    priority: 'critical',
    author_id: 'author-1',
    assignee_id: 'user-alice',
    assignee: mockUser,
    author: null,
    client_url: 'https://prod.myapp.com',
    client_summary: null,
    created_at: '2026-05-14T12:00:00Z',
    updated_at: '2026-05-14T12:00:00Z',
    description: null,
  },
  {
    id: '2',
    ticket_number: 102,
    title: 'Implement Google OAuth2 Single Sign-On layer',
    status: 'in_progress',
    priority: 'high',
    author_id: 'author-1',
    assignee_id: 'user-alice',
    assignee: mockUser,
    author: null,
    client_url: null,
    client_summary: null,
    created_at: '2026-05-15T08:00:00Z',
    updated_at: '2026-05-15T10:00:00Z',
    description: null,
  },
  {
    id: '3',
    ticket_number: 103,
    title: 'Fix typo in user profile description fallback text',
    status: 'closed',
    priority: 'low',
    author_id: 'author-1',
    assignee_id: null,
    assignee: null,
    author: null,
    client_url: null,
    client_summary: null,
    created_at: '2026-05-13T15:00:00Z',
    updated_at: '2026-05-13T17:00:00Z',
    description: null,
  },
];

const baseFilters: TicketFilters = {
  page: 1,
  size: 20,
};

export const Populated: Story = {
  args: {
    tickets: mockTickets,
    total: mockTickets.length,
    filters: baseFilters,
    isLoading: false,
    onFiltersChange: fn(),
    onDeleteTicket: async () => {},
    users: [mockUser],
  },
};

export const Loading: Story = {
  args: {
    tickets: [],
    total: 0,
    filters: baseFilters,
    isLoading: true,
    onFiltersChange: fn(),
    onDeleteTicket: async () => {},
  },
};

export const EmptyState: Story = {
  args: {
    tickets: [],
    total: 0,
    filters: baseFilters,
    isLoading: false,
    onFiltersChange: fn(),
    onDeleteTicket: async () => {},
  },
};

export const ActiveFiltersNoResults: Story = {
  args: {
    tickets: [],
    total: 0,
    filters: {
      ...baseFilters,
      search: 'missing keyword that doesn\'t exist',
    },
    isLoading: false,
    onFiltersChange: fn(),
    onDeleteTicket: async () => {},
  },
};
