<?php
use Illuminate\Support\Facades\Route;
use App\Http\Controllers\{
    MedicationController,
    ReminderController,
    DashboardController
};

Route::middleware(['auth','verified'])->group(function() {
    Route::get('/dashboard', [DashboardController::class,'index'])->name('dashboard');
    Route::resource('medications', MedicationController::class);
    Route::resource('reminders', ReminderController::class);
});

Route::middleware(['auth','role:admin'])->prefix('admin')->name('admin.')->group(function() {
    Route::resource('users', App\Http\Controllers\Admin\UserController::class);
    Route::get('settings', [App\Http\Controllers\Admin\SettingsController::class,'index'])->name('settings');
});

require __DIR__.'/auth.php';