<?php
namespace App\Models;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;

class Medication extends Model {
    use HasFactory;
    protected $fillable = ['user_id','name','dosage','start_date','end_date'];
    public function reminders() { return $this->hasMany(Reminder::class); }}
