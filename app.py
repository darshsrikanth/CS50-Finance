import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Set up Flask application
app = Flask(__name__)

# Custom filter to format prices in USD
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Set up database
db = SQL("sqlite:///finance.db")

# Make sure responses are not cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Display user's portfolio"""

    # Get user's stock data
    stocks = db.execute("SELECT symbol, SUM(shares) as total_shares FROM transactions WHERE user_id = :user_id GROUP by symbol HAVING total_shares > 0", user_id=session["user_id"])

    # Get user's current cash
    cash = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id=session["user_id"])[0]["cash"]

    # Calculate total value of user's stocks
    total_value = 0
    for stock in stocks:
        quote = lookup(stock["symbol"])
        stock["price"] = quote["price"]
        stock["value"] = stock["price"] * stock["total_shares"]
        total_value += stock["value"]

    # Total portfolio value (cash + stocks)
    grand_total = cash + total_value

    # Convert values to USD format
    cash = usd(cash)
    total_value = usd(total_value)
    grand_total = usd(grand_total)

    # Render portfolio page
    return render_template("index.html", stocks=stocks, cash=cash, total_value=total_value, grand_total=grand_total)

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy stocks"""
    if request.method == "POST":
        # Get the symbol and number of shares
        symbol = request.form.get("symbol").upper()
        shares = request.form.get("shares")

        # Validate input
        if not symbol:
            return apology("please provide the symbol")
        elif not shares or not shares.isdigit() or int(shares) <= 0:
            return apology("please provide a valid number of shares")

        # Lookup stock price
        quote = lookup(symbol)
        if quote is None:
            return apology("symbol not found")

        # Calculate the total cost
        price = quote["price"]
        total_cost = int(shares) * price

        # Check if user has enough cash
        cash = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id=session["user_id"])[0]["cash"]
        if cash < total_cost:
            return apology("insufficient cash")

        # Update user's cash and add transaction to history
        db.execute("UPDATE users SET cash = cash - :total_cost WHERE id = :user_id", total_cost=total_cost, user_id=session["user_id"])
        db.execute("INSERT INTO transactions (user_id, symbol, shares, price) VALUES(:user_id, :symbol, :shares, :price)",
                   user_id=session["user_id"], symbol=symbol, shares=shares, price=price)

        flash(f"Purchased {shares} shares of {symbol} for {usd(total_cost)}!")
        return redirect("/")

    # Render buy page
    else:
        return render_template("buy.html")

@app.route("/history")
@login_required
def history():
    """Show transaction history"""
    transactions = db.execute("SELECT * FROM transactions WHERE user_id = :user_id ORDER BY timestamp DESC", user_id=session["user_id"])
    return render_template("history.html", transactions=transactions)

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""
    session.clear()  # Log out any user that is already logged in

    if request.method == "POST":
        # Ensure username and password were submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Check username and password
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Log user in by storing their ID in session
        session["user_id"] = rows[0]["id"]

        return redirect("/")

    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""
    session.clear()  # Clear session data
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote"""
    if request.method == "POST":
        # Get stock symbol
        symbol = request.form.get("symbol")
        quote = lookup(symbol)

        # If no stock found, return an error
        if not quote:
            return apology("Sorry, but the symbol is wrong.", 400)

        # Show stock quote
        return render_template("quote.html", quote=quote)

    # Render quote page
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register new user"""
    session.clear()  # Log out any user that is already logged in

    if request.method == "POST":
        # Ensure username and passwords were submitted
        if not request.form.get("username"):
            return apology("please provide a username", 400)
        elif not request.form.get("password"):
            return apology("please provide a password", 400)
        elif not request.form.get("confirmation"):
            return apology("please confirm your password", 400)

        # Ensure passwords match
        if request.form.get("password") != request.form.get("confirmation"):
            return apology("passwords don't match", 400)

        # Check if username already exists
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))
        if len(rows) != 0:
            return apology("username already exists", 400)

        # Insert new user into database
        db.execute("INSERT INTO users (username, hash) VALUES(?, ?)", request.form.get("username"), generate_password_hash(request.form.get("password")))

        # Log in the newly registered user
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))
        session["user_id"] = rows[0]["id"]

        return redirect("/")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    # Get user's stocks
    stocks = db.execute("SELECT symbol, SUM(shares) as total_shares FROM transactions WHERE user_id = :user_id GROUP BY symbol HAVING total_shares > 0", user_id=session["user_id"])

    if request.method == "POST":
        # Get stock symbol and number of shares to sell
        symbol = request.form.get("symbol").upper()
        shares = request.form.get("shares")

        # Validate input
        if not symbol:
            return apology("must provide symbol")
        elif not shares or not shares.isdigit() or int(shares) <= 0:
            return apology("please provide a valid number of shares")

        shares = int(shares)

        # Check if user owns the stock
        for stock in stocks:
            if stock["symbol"] == symbol:
                if stock["total_shares"] < shares:
                    return apology("insufficient shares")

                # Sell the stock
                quote = lookup(symbol)
                if quote is None:
                    return apology("symbol not found")

                price = quote["price"]
                total_sale = shares * price

                # Update user's cash and log the sale
                db.execute("UPDATE users SET cash = cash + :total_sale WHERE id = :user_id", total_sale=total_sale, user_id=session["user_id"])
                db.execute("INSERT INTO transactions (user_id, symbol, shares, price) VALUES (:user_id, :symbol, :shares, :price)", user_id=session["user_id"], symbol=symbol, shares=-shares, price=price)

                flash(f"Sold {shares} shares of {symbol} for {usd(total_sale)}!")
                return redirect("/")

        return apology("unknown symbol")

    else:
        return render_template("sell.html", stocks=stocks)


@app.route("/add_cash", methods=["GET", "POST"])
@login_required
def add_cash():
    """Add cash to user's account"""
    if request.method == "POST":
        # Get the amount of cash to add
        amount = request.form.get("amount")

        # Validate input
        if not amount or not amount.isdigit() or int(amount) <= 0:
            return apology("please provide a valid amount", 400)

        # Update user's cash
        db.execute("UPDATE users SET cash = cash + :amount WHERE id = :user_id", amount=int(amount), user_id=session["user_id"])

        flash(f"Added {usd(int(amount))} to your account!")
        return redirect("/")

    else:
        return render_template("add_cash.html")
