export function authErrorMessage(error: {code?:string;message:string}):string {
  switch(error.code){
    case 'invalid_credentials': return 'Email hoặc mật khẩu chưa đúng, hoặc bạn chưa tạo tài khoản. Kiểm tra email (ví dụ @gmail.com), rồi chọn Tạo tài khoản nếu đây là lần đầu.'
    case 'email_not_confirmed': return 'Email chưa được xác nhận. Mở thư xác nhận khi đăng ký, sau đó quay lại đăng nhập.'
    case 'over_email_send_rate_limit': case 'over_request_rate_limit': return 'Bạn đã thử quá nhiều lần. Chờ ít phút rồi thử lại.'
    case 'email_address_not_authorized': return 'Máy chủ email hiện chưa cho phép gửi tới địa chỉ này. Cần cấu hình SMTP trong Supabase Auth trước khi đăng ký email bên ngoài.'
    case 'user_already_exists': return 'Email đã được đăng ký. Hãy chọn Đăng nhập.'
    default:return error.message
  }
}
export function normalizeAuthEmail(value:string):string {
  const email=value.trim().toLowerCase()
  if(!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email))throw new Error('Email phải có tên miền đầy đủ, ví dụ ten@gmail.com. Kiểm tra dấu chấm trước “com”.')
  return email
}
