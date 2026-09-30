# ขั้นตอนตรวจสอบเมื่อ BGP session หลุด

## อาการที่ควรสงสัย
BGP neighbor state เปลี่ยนเป็น Idle หรือ Active ค้างนานผิดปกติ

## ขั้นตอน
1. ตรวจ `show bgp neighbor` ดูค่า last error
2. ตรวจว่า TCP session (port 179) เชื่อมต่อได้หรือไม่
3. ถ้า neighbor อยู่คนละ AS ตรวจ policy ที่กรอง route ก่อนเสมอ
