"""
Authentication Routes – Enterprise Version

Provides:
- /auth/login
- /auth/logout
- /auth/seed-admin (first system bootstrap)

Enterprise Rules:
- Every User MUST be linked to a Personnel record.
- No orphan users allowed.
- Admin bootstrap creates BOTH Personnel and User.
"""

from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    flash,
    request,
)
from flask_login import (
    login_user,
    logout_user,
    login_required,
    current_user,
)

from ...extensions import db
from ...models import User, Personnel


auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


# ============================================================
# LOGIN
# ============================================================

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """
    Authenticate a user.

    Enterprise Logic:
    - Only active users may log in
    - Credentials validated via password hash
    """

    if current_user.is_authenticated:
        return redirect(url_for("procurements.list_procurements"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter_by(username=username).first()

        if not user or not user.check_password(password):
            flash("Λάθος όνομα χρήστη ή κωδικός.", "danger")
            return render_template("auth/login.html")

        if not user.is_active:
            flash("Ο λογαριασμός είναι ανενεργός.", "danger")
            return render_template("auth/login.html")

        login_user(user)
        flash("Καλώς ήρθατε!", "success")

        next_url = request.args.get("next")
        return redirect(next_url or url_for("procurements.list_procurements"))

    return render_template("auth/login.html")


# ============================================================
# LOGOUT
# ============================================================

@auth_bp.route("/logout")
@login_required
def logout():
    """Log out the current user."""
    logout_user()
    flash("Αποσυνδεθήκατε.", "info")
    return redirect(url_for("auth.login"))


# ============================================================
# SEED FIRST ADMIN (BOOTSTRAP)
# ============================================================

@auth_bp.route("/seed-admin", methods=["GET", "POST"])
def seed_admin():
    """
    Bootstrap the FIRST admin of the system.

    Enterprise Safety Rules:
    - If ANY user already exists → block
    - Admin MUST have linked Personnel record
    - Admin Personnel is system-generated
    """

    # If any user exists → prevent re-seeding
    if User.query.count() > 0:
        flash("Υπάρχει ήδη χρήστης στο σύστημα.", "warning")
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("Συμπληρώστε όνομα χρήστη και κωδικό.", "danger")
            return render_template("auth/seed_admin.html")

        # ----------------------------------------------------
        # 1️⃣ Create Personnel record for Admin
        # ----------------------------------------------------
        personnel = Personnel(
            agm="SYS-ADMIN-001",
            aem=None,
            rank="SYSTEM",
            specialty="SYSTEM",
            first_name="System",
            last_name="Administrator",
            is_active=True,
        )

        db.session.add(personnel)
        db.session.flush()  # Get personnel.id without full commit

        # ----------------------------------------------------
        # 2️⃣ Create User linked to Personnel
        # ----------------------------------------------------
        user = User(
            username=username,
            is_admin=True,
            is_active=True,
            personnel_id=personnel.id,
            service_unit_id=None,
        )

        user.set_password(password)

        db.session.add(user)
        db.session.commit()

        flash("Ο admin δημιουργήθηκε. Συνδεθείτε.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/seed_admin.html")