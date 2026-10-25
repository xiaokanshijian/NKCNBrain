const mysql = require('mysql')
if (!process.env.AUX_DB_PASSWORD) {
  throw new Error('Missing AUX_DB_PASSWORD for the optional Node service')
}
module.exports = mysql.createPool({
  host: process.env.AUX_DB_HOST || 'localhost',
  user: process.env.AUX_DB_USER || 'nkcn',
  password: process.env.AUX_DB_PASSWORD,
  database: process.env.AUX_DB_NAME || 'nkcn'
})
