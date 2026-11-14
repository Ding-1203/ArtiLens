const express = require("express")
const path = require("path")
const app = express()

const port = 3000

// 静态资源路径
app.use("/",express.static("static"))

app.listen(port, () => {
  console.log(`web server app listening on port ${port}`)
})