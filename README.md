# Medication Reminder App

## Deployment Guide

1. Clone Repository
   ```bash
   git clone https://github.com/marcosfermin/medreminder.git
   cd medreminder
````

2. Install Dependencies

   ```bash
   composer install --optimize-autoloader --no-dev
   npm install && npm run production
   ```

3. Configure Environment

   * Copy `.env.example` to `.env` and fill in values:

     ```ini
     APP_ENV=production
     APP_DEBUG=false
     APP_URL=https://your-domain.com

     DB_CONNECTION=mysql
     DB_HOST=127.0.0.1
     DB_PORT=3306
     DB_DATABASE=medreminder
     DB_USERNAME=your_db_user
     DB_PASSWORD=your_db_password

     TWILIO_SID=your_twilio_sid
     TWILIO_TOKEN=your_twilio_token
     TWILIO_FROM=+1234567890
     ```

4. Generate Application Key & Migrate

   ```bash
   php artisan key:generate
   php artisan migrate --force
   ```

5. Set File Permissions

   ```bash
   chown -R www-data:www-data storage bootstrap/cache
   chmod -R 775 storage bootstrap/cache
   ```

6. Configure Web Server

   * **Apache**: Create Virtual Host:

     ```apache
     <VirtualHost *:80>
         ServerName your-domain.com
         DocumentRoot /path/to/medreminder/public

         <Directory /path/to/medreminder/public>
             AllowOverride All
             Require all granted
         </Directory>

         ErrorLog ${APACHE_LOG_DIR}/medreminder_error.log
         CustomLog ${APACHE_LOG_DIR}/medreminder_access.log combined
     </VirtualHost>
     ```

     Enable mod\_rewrite: `a2enmod rewrite && service apache2 restart`

   * **Nginx**: Create server block:

     ```nginx
     server {
         listen 80;
         server_name your-domain.com;

         root /path/to/medreminder/public;
         index index.php index.html;

         location / {
             try_files $uri $uri/ /index.php?$query_string;
         }

         location ~ \.php$ {
             include snippets/fastcgi-php.conf;
             fastcgi_pass unix:/var/run/php/php8.1-fpm.sock;
         }

         location ~ /\.ht {
             deny all;
         }
     }
     ```

     Restart Nginx: `systemctl restart nginx`

7. Set Up Scheduler

   ```bash
   crontab -e
   ```

   Add:

   ```cron
   * * * * * cd /path/to/medreminder && php artisan schedule:run >> /dev/null 2>&1
   ```

8. SSL/TLS (Optional but recommended)

   * Install Certbot and obtain certificate:

     ```bash
     apt install certbot python3-certbot-apache
     certbot --apache -d your-domain.com
     ```

9. Queue Worker (Optional)
   If using queues for notifications:

   ```bash
   php artisan queue:work --daemon --sleep=3 --tries=3
   ```

10. Verify App

    * Visit `https://your-domain.com` in your browser.
    * Register a user, verify email, and test reminders.
