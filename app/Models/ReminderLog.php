<?php
namespace App\Models;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;

class ReminderLog extends Model {
    use HasFactory;
    protected $fillable = ['reminder_id','sent_at','status','error_message'];
}
