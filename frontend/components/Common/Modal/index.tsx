'use client';

import { Fragment, useRef, useEffect, useCallback } from 'react';
import { Transition, Dialog } from '@headlessui/react';
import { XMarkIcon } from '@heroicons/react/24/outline';

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  subTitle?: string;
  children?: React.ReactNode;
  /* Action buttons */
  onOk?: () => void;
  okText?: string;
  okDisabled?: boolean;
  okLoading?: boolean;
  onCancel?: () => void;
  cancelText?: string;
  /* Sizing */
  size?: 'sm' | 'md' | 'lg';
}

export default function Modal({
  open,
  onClose,
  title,
  subTitle,
  children,
  onOk,
  okText = 'Confirm',
  okDisabled = false,
  okLoading = false,
  onCancel,
  cancelText = 'Cancel',
  size = 'md',
}: ModalProps) {
  const cancelButtonRef = useRef<HTMLButtonElement>(null);

  const sizeClasses = {
    sm: 'sm:max-w-md',
    md: 'sm:max-w-lg',
    lg: 'sm:max-w-2xl',
  };

  const handleCancel = useCallback(() => {
    if (onCancel) {
      onCancel();
    } else {
      onClose();
    }
  }, [onCancel, onClose]);

  return (
    <Transition show={open} as={Fragment}>
      <Dialog
        as="div"
        className="relative z-50"
        initialFocus={cancelButtonRef}
        onClose={onClose}
      >
        {/* Backdrop */}
        <Transition.Child
          as={Fragment}
          enter="ease-out duration-300"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in duration-200"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-background/80 backdrop-blur-sm" />
        </Transition.Child>

        {/* Modal container */}
        <div className="fixed inset-0 z-50 overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4 text-center sm:p-0">
            <Transition.Child
              as={Fragment}
              enter="ease-out duration-300"
              enterFrom="opacity-0 scale-95"
              enterTo="opacity-100 scale-100"
              leave="ease-in duration-200"
              leaveFrom="opacity-100 scale-100"
              leaveTo="opacity-0 scale-95"
            >
              <Dialog.Panel
                className={`relative w-full transform overflow-hidden rounded-xl border border-border bg-card px-6 pb-6 pt-5 text-left shadow-xl transition-all sm:my-8 ${sizeClasses[size]}`}
              >
                {/* Close button */}
                <button
                  type="button"
                  className="absolute right-4 top-4 rounded-lg p-1 text-muted-foreground transition hover:bg-surface2 hover:text-foreground"
                  onClick={onClose}
                >
                  <XMarkIcon className="h-5 w-5" />
                </button>

                {/* Header */}
                {(title || subTitle) && (
                  <div className="mb-4 pr-8">
                    {title && (
                      <Dialog.Title className="text-gradient text-xl font-bold">
                        {title}
                      </Dialog.Title>
                    )}
                    {subTitle && (
                      <p className="mt-1 text-sm text-muted-foreground">{subTitle}</p>
                    )}
                  </div>
                )}

                {/* Content */}
                {children && <div className="text-muted-foreground">{children}</div>}

                {/* Actions */}
                {(onOk || onCancel) && (
                  <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
                    <button
                      type="button"
                      ref={cancelButtonRef}
                      onClick={handleCancel}
                      className="rounded-lg border border-border-strong bg-transparent px-4 py-2.5 text-sm font-medium text-muted-foreground transition hover:bg-surface2 hover:text-foreground"
                    >
                      {cancelText}
                    </button>
                    {onOk && (
                      <button
                        type="button"
                        onClick={onOk}
                        disabled={okDisabled || okLoading}
                        className="rounded-lg bg-gradient-to-r from-primary to-accent2 px-4 py-2.5 text-sm font-medium text-primary-foreground shadow-lg shadow-primary/25 transition hover:from-primary hover:to-accent2 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {okLoading ? 'Loading...' : okText}
                      </button>
                    )}
                  </div>
                )}
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition>
  );
}

