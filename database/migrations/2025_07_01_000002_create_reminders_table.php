<?php
use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration {
    public function up() {
        Schema::create('reminders', function (Blueprint $table) {
            $table->id();
            $table->foreignId('medication_id')->constrained()->cascadeOnDelete();
            $table->time('time_of_day');
            $table->enum('method',['sms','call']);
            $table->text('message_template')->nullable();
            $table->dateTime('next_run')->nullable();
            $table->timestamps();
        });
    }
    public function down() { Schema::dropIfExists('reminders'); }
};