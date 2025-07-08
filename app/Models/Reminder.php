<?php
namespace App\Models;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;

class Reminder extends Model {
    use HasFactory;
    protected $fillable = ['medication_id','time_of_day','method','message_template','next_run'];
    public function medication() { return $this->belongsTo(Medication::class); }
    public function user() { return $this->medication->user; }
    public function logs() { return $this->hasMany(ReminderLog::class); }
}