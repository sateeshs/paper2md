import type { Metadata } from "next";
import { SATForm } from "./components/SATForm";

export const metadata: Metadata = {
  title: "SAT Tutor — paper2md",
  description: "Paste any SAT question and get a step-by-step explanation powered by AI.",
};

export default function SATPage() {
  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-3xl mx-auto px-6 py-10 space-y-8">
        {/* Hero */}
        <div className="text-center space-y-3 py-6">
          <h1 className="text-4xl font-bold tracking-tight text-zinc-900">
            SAT Tutor
          </h1>
          <p className="text-zinc-500 text-lg max-w-xl mx-auto">
            Paste any SAT question — Math, Reading, or English — and get a
            step-by-step explanation, hints, and strategy tips.
          </p>
        </div>

        {/* Form + live response */}
        <SATForm />
      </div>
    </div>
  );
}
