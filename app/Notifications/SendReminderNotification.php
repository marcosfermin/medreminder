<?php
namespace App\Notifications;
use Illuminate\Notifications\Notification;
use Twilio\Rest\Client;

class SendReminderNotification extends Notification {
    protected $reminder;
    public function __construct($reminder) { $this->reminder = $reminder; }
    public function via($notifiable) { return ['twilio']; }
    public function toTwilio($notifiable) {
        $client = new Client(config('services.twilio.sid'),config('services.twilio.token'));
        if ($this->reminder->method === 'sms') {
            return $client->messages->create(
                $notifiable->phone,
                ['from'=>config('services.twilio.from'),'body'=>$this->reminder->message_template]
            );
        }
        return $client->calls->create(
            $notifiable->phone,
            config('services.twilio.from'),
            ['twiml'=>"<Response><Say>{$this->reminder->message_template}</Say></Response>"]
        );
    }}
