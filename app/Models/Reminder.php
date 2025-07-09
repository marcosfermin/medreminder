<?php
namespace App\Models;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;

class Reminder extends Model {
    use HasFactory;
    protected $fillable = ['medication_id','time_of_day','method','message_template','next_run'];
    public function medication() { return $this->belongsTo(Medication::class); }
    public function user() {
        return $this->hasOneThrough(
            User::class,
            Medication::class,
            'id',       // medications.id
            'id',       // users.id
            'medication_id',
            'user_id'
        );
    }
    public function logs() { return $this->hasMany(ReminderLog::class); }}

