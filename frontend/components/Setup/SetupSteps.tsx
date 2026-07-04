'use client';

import { CheckIcon } from '@heroicons/react/24/solid';

interface SetupStepProps {
  stepNumber: number;
  title: string;
  description?: string;
  active?: boolean;
  completed?: boolean;
  isLastStep?: boolean;
}

export default function SetupStep({
  stepNumber,
  title,
  description,
  active = false,
  completed = false,
  isLastStep = false,
}: SetupStepProps) {
  return (
    <li className="relative md:flex md:flex-1">
      <div className="flex items-center gap-4 px-4 py-4 text-sm font-medium md:px-6">
        {/* Step circle */}
        <div
          className={`flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full border-2 transition-all duration-200
            ${active ? 'border-primary bg-primary/10' : 'border-border-strong'}
            ${completed ? 'border-success bg-success' : ''}`}
        >
          {completed ? (
            <CheckIcon className="h-5 w-5 text-foreground" />
          ) : (
            <span className={`text-sm font-semibold ${active ? 'text-primary' : 'text-muted-foreground'}`}>
              {stepNumber}
            </span>
          )}
        </div>

        {/* Step text */}
        <div className="flex flex-col">
          <span
            className={`text-sm font-medium transition-colors ${
              active ? 'text-foreground' : completed ? 'text-success' : 'text-muted-foreground'
            }`}
          >
            {title}
          </span>
          {description && (
            <span className="text-xs text-faint">{description}</span>
          )}
        </div>
      </div>

      {/* Connector line (hidden on mobile, shown on md+) */}
      {!isLastStep && (
        <div className="absolute right-0 top-0 hidden h-full w-5 md:block">
          <svg
            className="h-full w-full text-faint"
            viewBox="0 0 22 80"
            fill="none"
            preserveAspectRatio="none"
          >
            <path
              d="M0 -2L20 40L0 82"
              vectorEffect="non-scaling-stroke"
              stroke="currentColor"
              strokeLinejoin="round"
            />
          </svg>
        </div>
      )}
    </li>
  );
}

interface SetupStepsProps {
  currentStep: number;
  steps: { title: string; description?: string }[];
}

export function SetupSteps({ currentStep, steps }: SetupStepsProps) {
  return (
    <nav className="relative z-10">
      <ul className="divide-y divide-border rounded-lg border border-border bg-card/50 backdrop-blur-sm md:flex md:divide-y-0">
        {steps.map((step, index) => (
          <SetupStep
            key={index}
            stepNumber={index + 1}
            title={step.title}
            description={step.description}
            active={currentStep === index + 1}
            completed={currentStep > index + 1}
            isLastStep={index === steps.length - 1}
          />
        ))}
      </ul>
    </nav>
  );
}

