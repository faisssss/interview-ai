import { MeetingList } from "@/components/MeetingList";
import { UploadForm } from "@/components/UploadForm";

export default function Home() {
  return (
    <main className="mx-auto w-full max-w-3xl space-y-10 px-4 py-12">
      <header className="space-y-2">
        <h1 className="text-3xl font-bold tracking-tight">Your meetings, remembered.</h1>
        <p className="text-slate-600 dark:text-slate-400">
          Upload a recording to get a transcript with speakers, a summary, action items and
          decisions.
        </p>
      </header>
      <UploadForm />
      <MeetingList />
    </main>
  );
}
