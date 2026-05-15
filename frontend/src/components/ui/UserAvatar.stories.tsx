import type { Meta, StoryObj } from '@storybook/react';
import { UserAvatar } from './UserAvatar';

/**
 * UserAvatar handles circular profile renders. It accepts absolute image 
 * URLs (such as Google user avatars) and automatically switches to dynamic
 * single-letter colored fallback icons if loading fails or sources are null.
 */
const meta: Meta<typeof UserAvatar> = {
  title: 'UI/UserAvatar',
  component: UserAvatar,
  tags: ['autodocs', 'ai-generated'],
  argTypes: {
    src: {
      control: 'text',
      description: 'Direct HTTP URI pointing to an avatar bitmap/svg.',
    },
    name: {
      control: 'text',
      description: 'Used for generating initials during graceful fallbacks.',
    },
    size: {
      control: 'select',
      options: ['xs', 'sm', 'md', 'lg'],
      description: 'Controls diameter dimensions.',
    },
  },
};

export default meta;
type Story = StoryObj<typeof UserAvatar>;

/** Renders an image from a valid external source URL. */
export const WithImage: Story = {
  args: {
    src: 'https://api.dicebear.com/7.x/bottts/svg?seed=jane',
    name: 'Jane Doe',
    size: 'md',
  },
};

/** Automatically falls back to initials when src is null. */
export const FallbackInitials: Story = {
  args: {
    src: null,
    name: 'Alex Morgan',
    size: 'md',
  },
};

/** Smallest profile avatar used in inline comment threads. */
export const Small: Story = {
  args: {
    src: 'https://api.dicebear.com/7.x/bottts/svg?seed=alex',
    name: 'Alex Morgan',
    size: 'sm',
  },
};

/** Large diameter configuration matching personal profiles settings views. */
export const Large: Story = {
  args: {
    src: null,
    name: 'Administrator User',
    size: 'lg',
  },
};
