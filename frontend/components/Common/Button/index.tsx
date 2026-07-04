'use client';

import React, { forwardRef } from 'react';
import Link from 'next/link';
import { twMerge } from 'tailwind-merge';

export type ButtonType =
  | 'default'
  | 'primary'
  | 'danger'
  | 'warning'
  | 'success'
  | 'ghost';

export type ButtonSize = 'sm' | 'md' | 'lg';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  buttonType?: ButtonType;
  buttonSize?: ButtonSize;
  href?: string;
  children: React.ReactNode;
}

const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      buttonType = 'default',
      buttonSize = 'md',
      href,
      children,
      className,
      disabled,
      ...props
    },
    ref
  ) => {
    const baseStyles =
      'inline-flex items-center justify-center border font-medium rounded-lg focus:outline-none transition ease-in-out duration-150 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap';

    // NOTE: do not use legacy `bg-opacity-*` here — tailwind-merge treats it as
    // conflicting with `bg-{color}` and strips the color, leaving a transparent
    // button. Use solid tokens with `/opacity` hover states instead.
    const typeStyles: Record<ButtonType, string> = {
      primary:
        'text-primary-foreground border-primary bg-primary hover:bg-primary/90 hover:border-primary focus:ring-2 focus:ring-ring focus:ring-offset-2 focus:ring-offset-background',
      danger:
        'text-destructive-foreground border-destructive bg-destructive hover:bg-destructive/90 hover:border-destructive focus:ring-2 focus:ring-destructive focus:ring-offset-2 focus:ring-offset-background',
      warning:
        'text-warning-foreground border-warning bg-warning hover:bg-warning/90 hover:border-warning focus:ring-2 focus:ring-warning focus:ring-offset-2 focus:ring-offset-background',
      success:
        'text-success-foreground border-success bg-success hover:bg-success/90 hover:border-success focus:ring-2 focus:ring-success focus:ring-offset-2 focus:ring-offset-background',
      ghost:
        'text-foreground bg-surface2 border-border-strong hover:bg-surface2/70 hover:text-foreground hover:border-border-strong focus:ring-2 focus:ring-border-strong focus:ring-offset-2 focus:ring-offset-background',
      default:
        'text-foreground bg-card border-border-strong hover:text-foreground hover:bg-surface2 hover:border-border-strong focus:ring-2 focus:ring-border-strong focus:ring-offset-2 focus:ring-offset-background',
    };

    const sizeStyles: Record<ButtonSize, string> = {
      sm: 'px-3 py-1.5 text-xs gap-1.5',
      md: 'px-4 py-2 text-sm gap-2',
      lg: 'px-6 py-3 text-base gap-2.5',
    };

    const classes = twMerge(
      baseStyles,
      typeStyles[buttonType],
      sizeStyles[buttonSize],
      className
    );

    if (href) {
      return (
        <Link href={href} className={classes}>
          {children}
        </Link>
      );
    }

    return (
      <button ref={ref} className={classes} disabled={disabled} {...props}>
        {children}
      </button>
    );
  }
);

Button.displayName = 'Button';

export default Button;

