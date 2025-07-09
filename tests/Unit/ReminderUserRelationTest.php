<?php

namespace Tests\Unit;

use App\Models\Medication;
use App\Models\Reminder;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class ReminderUserRelationTest extends TestCase
{
    use RefreshDatabase;

    public function test_reminder_with_user_eager_loads_user(): void
    {
        $user = User::factory()->create();
        $medication = Medication::create([
            'user_id' => $user->id,
            'name' => 'Test Med',
            'dosage' => '1 pill',
            'start_date' => now()->toDateString(),
        ]);
        Reminder::create([
            'medication_id' => $medication->id,
            'time_of_day' => '08:00:00',
            'method' => 'sms',
            'message_template' => 'Take meds',
            'next_run' => now(),
        ]);

        $reminder = Reminder::with('user')->first();

        $this->assertTrue($reminder->relationLoaded('user'));
        $this->assertEquals($user->id, $reminder->user->id);
    }
}
