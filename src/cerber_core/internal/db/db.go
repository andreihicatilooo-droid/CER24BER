package db

import (
	"github.com/jmoiron/sqlx"
	_ "github.com/lib/pq"
)

// Connect opens and validates a PostgreSQL connection pool.
func Connect(dsn string) (*sqlx.DB, error) {
	database, err := sqlx.Connect("postgres", dsn)
	if err != nil {
		return nil, err
	}
	database.SetMaxOpenConns(25)
	database.SetMaxIdleConns(5)
	return database, nil
}
