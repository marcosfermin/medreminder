<?php
namespace App\Console\Commands;
use Illuminate\Console\Command;
use App\Models\Reminder;

class SendReminders extends Command {
    protected $signature = 'reminders:send';
    protected $description = 'Send due SMS and voice reminders';
    public function handle() {
        Reminder::where('next_run','<=',now())
            ->with(['medication.user'])
            ->get()
            ->each(fn($reminder) => $this->process($reminder));
    }
    protected function process($r) {
        try {
            $r->medication->user->notify(new \App\Notifications\SendReminderNotification($r));
            $r->logs()->create(['status'=>'sent','sent_at'=>now()]);
        } catch (\Exception $e) {
            $r->logs()->create(['status'=>'failed','error_message'=>$e->getMessage(),'sent_at'=>now()]);
        }
        $r->update(['next_run'=>now()->addDay()]);
    }}
