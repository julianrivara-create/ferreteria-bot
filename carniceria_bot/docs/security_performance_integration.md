# 🔐 Security & Performance Integration Examples

## 1. Using Cache in Business Logic

```python
from bot_sales.core.cache_manager import cached, invalidate_cache
from bot_sales.core.business_logic import BusinessLogic

class BusinessLogic:
    
    @cached('products', ttl=300)  # Cache for 5 minutes
    def buscar_stock(self, modelo, storage_gb=None, color=None):
        """
        Search products with caching
        Cache key automatically generated from parameters
        """
        # Expensive database query here
        results = self.db.find_matches(modelo, storage_gb, color)
        return results
    
    def actualizar_stock(self, sku, new_qty):
        """When updating stock, invalidate cache"""
        self.db.update_stock(sku, new_qty)
        
        # Clear all product caches
        invalidate_cache('products')
```

## 2. Using PII Encryption

```python
from bot_sales.security.encryption import encrypt_customer_data, decrypt_customer_data

# Before saving to database
customer_data = {
    'nombre': 'Juan Pérez',
    'email': 'juan@example.com',
    'phone': '+541122334455',
    'dni': '12345678'
}

# Encrypt PII fields
encrypted = encrypt_customer_data(customer_data)
db.save(encrypted)

# When retrieving from database
encrypted_customer = db.get(customer_id)
decrypted = decrypt_customer_data(encrypted_customer)
print(decrypted['email'])  # juan@example.com
```

## 3. Using JWT Authentication in Dashboard

```python
from flask import Flask, request, jsonify
from bot_sales.security.auth import require_auth, get_auth_manager, get_user_database

app = Flask(__name__)

# Login endpoint
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    # Authenticate
    user_db = get_user_database()
    user = user_db.authenticate(username, password)
    
    if not user:
        return jsonify({'error': 'Invalid credentials'}), 401
    
    # Generate token
    auth = get_auth_manager()
    token = auth.generate_token(user['user_id'], user['role'])
    
    return jsonify({
        'token': token,
        'user': user
    })

# Protected endpoint - any authenticated user
@app.route('/api/profile')
@require_auth()
def get_profile():
    user = request.user  # Injected by decorator
    return jsonify(user)

# Admin-only endpoint
@app.route('/api/admin/users')
@require_auth('admin')
def list_users():
    # Only admins can access
    return jsonify({'users': [...]})

# Manager or admin endpoint
@app.route('/api/reports')
@require_auth('manager')
def get_reports():
    # Managers and admins can access
    return jsonify({'reports': [...]})
```

## 4. Using Background Tasks

```python
from bot_sales.core.async_ops import run_in_background, queue_task
from bot_sales.integrations.email_client import send_email

# Decorator approach
@run_in_background
def send_confirmation_email(customer_email, order_id):
    """This runs in background thread"""
    send_email(
        to=customer_email,
        subject=f"Order {order_id} confirmed!",
        body="Thank you for your purchase..."
    )

# Direct queue approach
def confirm_sale(hold_id, zona, metodo_pago):
    # ... sale confirmation logic ...
    
    # Queue email to send in background
    queue_task(
        send_confirmation_email,
        customer_email='user@example.com',
        order_id=sale_id
    )
    
    return {'status': 'success', 'sale_id': sale_id}
```

## 5. Using State Machine

```python
from bot_sales.core.state_machine import get_state_machine, validate_order_transition

def update_order_status(order_id, new_status, user_id):
    """
    Update order status with validation
    """
    # Get current order
    order = db.get_order(order_id)
    current_status = order['status']
    
    # Validate transition
    is_valid, error = validate_order_transition(current_status, new_status)
    
    if not is_valid:
        return {'error': error}, 400
    
    # Perform transition with audit log
    sm = get_state_machine()
    success, error = sm.transition(
        order_id=order_id,
        current_state=current_status,
        new_state=new_status,
        user_id=user_id,
        reason=f"Updated by {user_id}"
    )
    
    if not success:
        return {'error': error}, 400
    
    # Update database
    db.update_order_status(order_id, new_status)
    
    return {'status': 'success'}

# Get audit log for order
sm = get_state_machine()
audit_log = sm.get_audit_log(order_id='ORD-123')
```

## 6. Using Monitoring

```python
from bot_sales.core.monitoring import track_errors, track_performance, get_monitoring

# Decorator for automatic error tracking
@track_errors
def risky_operation():
    # Any exception is automatically sent to Sentry
    result = external_api_call()
    return result

# Performance tracking
@track_performance('api.chatgpt')
def call_chatgpt(messages):
    # Performance metrics sent to Sentry
    response = client.send_message(messages)
    return response

# Manual error tracking with context
monitoring = get_monitoring()

try:
    process_payment(order_id)
except Exception as e:
    monitoring.capture_exception(e, context={
        'order_id': order_id,
        'user_id': user_id,
        'amount': amount
    })
```

## 7. Complete Integration Example

```python
from bot_sales.core.cache_manager import cached
from bot_sales.core.async_ops import queue_task
from bot_sales.security.encryption import encrypt_customer_data
from bot_sales.core.monitoring import track_errors, get_monitoring

class EnhancedBusinessLogic(BusinessLogic):
    
    @cached('products', ttl=300)
    @track_errors
    def buscar_stock(self, modelo, storage_gb=None, color=None):
        """
        Cached product search with error tracking
        """
        monitoring = get_monitoring()
        monitoring.add_breadcrumb(
            message=f"Searching for {modelo}",
            category="product_search"
        )
        
        results = self.db.find_matches(modelo, storage_gb, color)
        return results
    
    @track_errors
    def crear_reserva(self, sku, nombre, contacto, email=None):
        """
        Create hold with PII encryption and async email
        """
        # Create hold
        hold_data = {
            'sku': sku,
            'nombre': nombre,
            'contacto': contacto,
            'email': email
        }
        
        # Encrypt PII before saving
        encrypted_hold = encrypt_customer_data(hold_data)
        hold_id = self.db.create_hold(encrypted_hold)
        
        # Send confirmation email in background
        if email:
            queue_task(
                send_email,
                to=email,
                subject="Reserva confirmada",
                body=f"Tu reserva {hold_id} fue creada"
            )
        
        return {
            'status': 'success',
            'hold_id': hold_id
        }
```

## Environment Variables Required

```bash
# .env file
REDIS_URL=redis://localhost:6379/0
JWT_SECRET=your-secret-key-here
ENCRYPTION_PASSWORD=your-encryption-password
ENCRYPTION_SALT=your-salt-here
SENTRY_DSN=your-sentry-dsn
```

## Testing

Run all new tests:
```bash
pytest tests/test_auth.py -v
pytest tests/test_cache.py -v
pytest tests/test_validators.py -v
pytest tests/test_sanitizer.py -v
```

Coverage report:
```bash
pytest tests/ --cov=bot_sales --cov-report=html
open htmlcov/index.html
```
