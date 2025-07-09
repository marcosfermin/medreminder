<?php
namespace App\Models;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;

class ReminderLog extends Model {
    use HasFactory;
    protected $fillable = ['reminder_id','status','error_message','sent_at'];
    public function reminder() { return $this->belongsTo(Reminder::class); }
}
