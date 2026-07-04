'use client';

import React, { forwardRef } from 'react';
import Link from 'next/link';
import { twMerge } from 'tailwind-merge';

export type BadgeType =
  | 'default'
  | 'primary'
  | 'danger'
  | 'warning'
  | 'success'
  | 'dark'
  | 'light';

interface BadgeProps {
  badgeType?: BadgeType;
  className?: string;
  href?: string;
  children: React.ReactNode;
}

const Badge = forwardRef<HTMLElement, BadgeProps>(
  ({ badgeType = 'default', className, href, children }, ref) => {
    const baseStyles =
      'px-2.5 py-0.5 inline-flex text-xs leading-5 font-semibold rounded-full whitespace-nowrap';

    const typeStyles: Record<BadgeType, string> = {
      default:
        'bg-primary/80 border border-primary text-primary-foreground',
      primary:
        'bg-primary/80 border border-primary text-primary-foreground',
      danger:
        'bg-destructive/80 border border-destructive text-destructive-foreground',
      warning:
        'bg-warning/80 border border-warning text-warning-foreground',
      success:
        'bg-success/80 border border-success text-success-foreground',
      dark:
        'bg-background border border-border text-muted-foreground',
      light:
        'bg-surface2 border border-border-strong text-muted-foreground',
    };

    const hoverStyles: Record<BadgeType, string> = {
      default: 'hover:bg-primary/90',
      primary: 'hover:bg-primary/90',
      danger: 'hover:bg-destructive/90',
      warning: 'hover:bg-warning',
      success: 'hover:bg-success/90',
      dark: 'hover:bg-card',
      light: 'hover:bg-surface2',
    };

    const classes = twMerge(
      baseStyles,
      typeStyles[badgeType],
      href && `transition cursor-pointer ${hoverStyles[badgeType]}`,
      !href && 'cursor-default',
      className
    );

    // External link
    if (href?.includes('://')) {
      return (
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className={classes}
          ref={ref as React.Ref<HTMLAnchorElement>}
        >
          {children}
        </a>
      );
    }

    // Internal link
    if (href) {
      return (
        <Link
          href={href}
          className={classes}
          ref={ref as React.Ref<HTMLAnchorElement>}
        >
          {children}
        </Link>
      );
    }

    // Plain badge
    return (
      <span className={classes} ref={ref as React.Ref<HTMLSpanElement>}>
        {children}
      </span>
    );
  }
);

Badge.displayName = 'Badge';

export default Badge;

