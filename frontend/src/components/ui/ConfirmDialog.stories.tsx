import type { Meta, StoryObj } from '@storybook/react';
import { fn } from 'storybook/test';
import { ConfirmDialog } from './ConfirmDialog';

/**
 * ConfirmDialog is a modal pop-up used to intercept destructive operations
 * (e.g., deleting a ticket, discarding unsaved data) and request definitive
 * acknowledgment from the system operator.
 */
const meta: Meta<typeof ConfirmDialog> = {
  title: 'UI/ConfirmDialog',
  component: ConfirmDialog,
  tags: ['autodocs', 'ai-generated'],
  parameters: {
    // Since dialogs render via portals at root, we pad the layout to display content
    layout: 'centered',
  },
  argTypes: {
    open: {
      control: 'boolean',
      description: 'Toggles the modal rendering state visibility.',
    },
    title: {
      control: 'text',
      description: 'Main short header warning.',
    },
    description: {
      control: 'text',
      description: 'Explanatory text detailing the impact of confirmation.',
    },
    confirmLabel: {
      control: 'text',
      description: 'String rendered inside the high-priority action button.',
    },
  },
};

export default meta;
type Story = StoryObj<typeof ConfirmDialog>;

/** The default deletion warning setup. */
export const DeleteTicket: Story = {
  args: {
    open: true,
    title: 'Delete Ticket',
    description: 'Are you sure you want to delete this ticket? This action is permanent and cannot be reversed.',
    confirmLabel: 'Delete',
    onConfirm: fn(),
    onCancel: fn(),
  },
};

/** Asks the user before leaving a complex unsaved context. */
export const DiscardChanges: Story = {
  args: {
    open: true,
    title: 'Discard Changes',
    description: 'You have unsubmitted edits in the ticket details. Leaving this screen will wipe all local updates.',
    confirmLabel: 'Discard',
    onConfirm: fn(),
    onCancel: fn(),
  },
};
