<?php

namespace Database\Factories;

use Illuminate\Database\Eloquent\Factories\Factory;
use App\Models\ReminderLog;

/**
 * @extends Factory<ReminderLog>
 */
class ReminderLogFactory extends Factory
{
    protected $model = ReminderLog::class;

    public function definition(): array
    {
        return [
            'sent_at' => $this->faker->dateTime(),
            'status' => 'sent',
            'error_message' => null,
        ];
    }
}
