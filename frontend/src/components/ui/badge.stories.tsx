import type { Meta, StoryObj } from '@storybook/react';
import { expect } from 'storybook/test';
import { Badge } from './badge';

/**
 * Badge component used for rendering inline status indicators,
 * priorities, and small taxonomy tags across the user interface.
 */
const meta: Meta<typeof Badge> = {
  title: 'UI/Badge',
  component: Badge,
  tags: ['autodocs', 'ai-generated'],
  argTypes: {
    variant: {
      control: 'select',
      options: [
        'default',
        'open',
        'in_progress',
        'in_review',
        'closed',
        'low',
        'medium',
        'high',
        'critical',
      ],
      description: 'Defines the color scheme matching status or priority.',
    },
    children: {
      control: 'text',
      description: 'Label displayed inside the badge.',
    },
  },
};

export default meta;
type Story = StoryObj<typeof Badge>;

/** The fallback style used for general information tokens. */
export const Default: Story = {
  args: {
    variant: 'default',
    children: 'Badge Label',
  },
  play: async ({ canvasElement }) => {
    // Check rendered content and element tagName to verify standard behavior
    const badge = canvasElement.querySelector('span');
    expect(badge).not.toBeNull();
    expect(badge?.textContent).toBe('Badge Label');
    
    // CssCheck: Verify standard border radius tailwind computed style (rounded-full)
    if (badge) {
      const style = window.getComputedStyle(badge);
      // In JSDOM/Chromium, rounded-full computes to a high pixel value (typically 9999px)
      expect(style.borderRadius).not.toBe('0px');
    }
  },
};


/** Indicates an unassigned or freshly created ticket. */
export const Open: Story = {
  args: {
    variant: 'open',
    children: 'Open',
  },
};

/** Indicates an issue currently being evaluated by an operator. */
export const InProgress: Story = {
  args: {
    variant: 'in_progress',
    children: 'In Progress',
  },
};

/** Indicates code execution or ticket updates requiring supervisor peer-review. */
export const InReview: Story = {
  args: {
    variant: 'in_review',
    children: 'In Review',
  },
};

/** Shows finalized transactions or resolved tickets. */
export const Closed: Story = {
  args: {
    variant: 'closed',
    children: 'Closed',
  },
};

/** Represents low severity issues. */
export const PriorityLow: Story = {
  args: {
    variant: 'low',
    children: 'Low Priority',
  },
};

/** Represents normal severity issues. */
export const PriorityMedium: Story = {
  args: {
    variant: 'medium',
    children: 'Medium Priority',
  },
};

/** Represents elevated severity issues. */
export const PriorityHigh: Story = {
  args: {
    variant: 'high',
    children: 'High Priority',
  },
};

/** Represents critical blocking escalations. */
export const PriorityCritical: Story = {
  args: {
    variant: 'critical',
    children: 'Critical',
  },
};
