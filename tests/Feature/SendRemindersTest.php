<?php

namespace Tests\Feature;

use Tests\TestCase;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Notification;
use Illuminate\Support\Facades\Artisan;
use App\Models\{User, Medication, Reminder, ReminderLog};

class SendRemindersTest extends TestCase
{
    use RefreshDatabase;

    public function test_command_creates_reminder_log(): void
    {
        Notification::fake();

        $user = User::factory()->create();
        $user->forceFill(['phone' => '+15555555555'])->save();

        $medication = Medication::create([
            'user_id' => $user->id,
            'name' => 'Test Med',
            'dosage' => '1 pill',
        ]);

        $reminder = Reminder::create([
            'medication_id' => $medication->id,
            'time_of_day' => '00:00:00',
            'method' => 'sms',
            'message_template' => 'Take your med',
            'next_run' => now()->subMinute(),
        ]);

        Artisan::call('reminders:send');

        $this->assertDatabaseHas('reminder_logs', [
            'reminder_id' => $reminder->id,
            'status' => 'sent',
        ]);
    }

    public function test_reminder_log_factory(): void
    {
        $user = User::factory()->create();
        $medication = Medication::create([
            'user_id' => $user->id,
            'name' => 'Factory Med',
        ]);
        $reminder = Reminder::create([
            'medication_id' => $medication->id,
            'time_of_day' => '01:00:00',
            'method' => 'sms',
            'message_template' => 'Another med',
            'next_run' => now()->addHour(),
        ]);

        $log = ReminderLog::factory()->for($reminder)->create();

        $this->assertDatabaseHas('reminder_logs', [
            'id' => $log->id,
            'reminder_id' => $reminder->id,
        ]);
    }
}
