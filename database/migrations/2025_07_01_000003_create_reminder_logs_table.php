<?php
use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration {
    public function up() {
        Schema::create('reminder_logs', function (Blueprint $table) {
            $table->id();
            $table->foreignId('reminder_id')->constrained()->cascadeOnDelete();
            $table->dateTime('sent_at')->nullable();
            $table->enum('status',['sent','failed'])->default('sent');
            $table->text('error_message')->nullable();
            $table->timestamps();
        });
    }
    public function down() { Schema::dropIfExists('reminder_logs'); }};
