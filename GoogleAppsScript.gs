/**
 * สคริปต์นี้ทำให้ Google Sheets เป็นฐานข้อมูลกลางออนไลน์
 * ให้ทั้งสาขาพระบาทและสาขาโลตัสปงสนุกซิงก์ข้อมูลมาที่ชีทเดียวกัน
 * และให้เจ้าของเปิด Google Sheets ดูภาพรวมทั้งร้านได้ทุกที่ทุกเวลา
 *
 * วิธีติดตั้ง: ดูขั้นตอนในแชท (สรุปคร่าวๆ)
 * 1. สร้าง Google Sheet ใหม่
 * 2. เมนู Extensions > Apps Script แล้ววางโค้ดทั้งไฟล์นี้แทนของเดิม
 * 3. รันฟังก์ชัน setupSheets() หนึ่งครั้งเพื่อสร้างตารางเริ่มต้น
 * 4. Deploy > New deployment > Web app
 *    - Execute as: Me
 *    - Who has access: Anyone
 * 5. คัดลอกลิงก์ Web App URL ที่ได้ ส่งกลับมาให้ Claude วางในแอพ
 */

var PRODUCT_FIELDS_ = ["id", "category", "brand", "model", "size", "costPrice", "sellPrice", "qty", "branch"];
var TRANSACTION_FIELDS_ = ["id", "type", "datetime", "productId", "productName", "qty", "unitPrice", "total", "staff", "branch"];

// รันครั้งเดียวตอนติดตั้งครั้งแรก (เมนู Run > setupSheets ใน Apps Script editor)
function setupSheets() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();

  var products = ss.getSheetByName("Products") || ss.insertSheet("Products");
  products.clearContents();
  products.appendRow(PRODUCT_FIELDS_);

  var transactions = ss.getSheetByName("Transactions") || ss.insertSheet("Transactions");
  transactions.clearContents();
  transactions.appendRow(TRANSACTION_FIELDS_);

  var summary = ss.getSheetByName("สรุป") || ss.insertSheet("สรุป");
  summary.clearContents();
  summary.getRange("A1").setValue("สรุปยอดรวมทั้งร้าน (อัปเดตอัตโนมัติเมื่อสาขาซิงก์ข้อมูลเข้ามา)");
  summary.getRange("A3:C3").setValues([["สาขา", "ยอดขายรวม (บาท)", "ต้นทุนรับของเข้ารวม (บาท)"]]);
  summary.getRange("A4").setValue("สาขาพระบาท");
  summary.getRange("A5").setValue("สาขาโลตัสปงสนุก");
  // Transactions คอลัมน์: A=id B=type C=datetime D=productId E=productName F=qty G=unitPrice H=total I=staff J=branch
  summary.getRange("B4").setFormula('=SUMIFS(Transactions!H:H,Transactions!B:B,"sale",Transactions!J:J,"phrabat")');
  summary.getRange("C4").setFormula('=SUMIFS(Transactions!H:H,Transactions!B:B,"restock",Transactions!J:J,"phrabat")');
  summary.getRange("B5").setFormula('=SUMIFS(Transactions!H:H,Transactions!B:B,"sale",Transactions!J:J,"lotus_pongsanuk")');
  summary.getRange("C5").setFormula('=SUMIFS(Transactions!H:H,Transactions!B:B,"restock",Transactions!J:J,"lotus_pongsanuk")');

  summary.getRange("A7").setValue("ดูสต๊อกคงเหลือแยกหมวด/สาขา: สร้าง Pivot Table เองได้จากแท็บ Products (Insert > Pivot table)");

  summary.autoResizeColumns(1, 3);
  SpreadsheetApp.flush();
}

function doGet(e) {
  var branch = e.parameter.branch;
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var products = readSheet_(ss.getSheetByName("Products"));
  var transactions = readSheet_(ss.getSheetByName("Transactions"));

  if (branch) {
    products = products.filter(function (p) { return p.branch === branch; });
    transactions = transactions.filter(function (t) { return t.branch === branch; });
  }

  return jsonResponse_({ ok: true, products: products, transactions: transactions });
}

function doPost(e) {
  try {
    var body = JSON.parse(e.postData.contents);
    var branch = body.branch;
    if (!branch) return jsonResponse_({ ok: false, error: "missing branch" });

    var ss = SpreadsheetApp.getActiveSpreadsheet();
    writeBranchData_(ss.getSheetByName("Products"), body.products || [], branch, PRODUCT_FIELDS_);
    writeBranchData_(ss.getSheetByName("Transactions"), body.transactions || [], branch, TRANSACTION_FIELDS_);

    return jsonResponse_({ ok: true });
  } catch (err) {
    return jsonResponse_({ ok: false, error: String(err) });
  }
}

// อ่านทุกแถวในชีทเป็น array ของ object ตามหัวตาราง
function readSheet_(sheet) {
  var values = sheet.getDataRange().getValues();
  var headers = values[0];
  var rows = [];
  for (var i = 1; i < values.length; i++) {
    if (values[i].every(function (c) { return c === ""; })) continue; // ข้ามแถวว่าง
    var row = {};
    for (var j = 0; j < headers.length; j++) {
      row[headers[j]] = values[i][j];
    }
    rows.push(row);
  }
  return rows;
}

// แทนที่ข้อมูลเฉพาะของสาขาที่ส่งมา โดยไม่แตะแถวของสาขาอื่น
function writeBranchData_(sheet, newRows, branch, fields) {
  var values = sheet.getDataRange().getValues();
  var headers = values[0];
  var branchCol = headers.indexOf("branch");

  var keep = [];
  for (var i = 1; i < values.length; i++) {
    if (values[i].every(function (c) { return c === ""; })) continue;
    if (values[i][branchCol] !== branch) keep.push(values[i]);
  }

  var incoming = newRows.map(function (obj) {
    return fields.map(function (f) { return obj[f] !== undefined ? obj[f] : ""; });
  });

  var finalRows = keep.concat(incoming);
  sheet.clearContents();
  sheet.appendRow(headers);
  if (finalRows.length > 0) {
    sheet.getRange(2, 1, finalRows.length, headers.length).setValues(finalRows);
  }
}

function jsonResponse_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
