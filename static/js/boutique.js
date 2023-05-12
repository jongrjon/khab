function purchasedItem(){
	if($("#purchasepopup").length){
		console.log("Purchase modal exists")
        	$('#purchasepopup').modal('show');
	};
};

function newProduct(e){
	e.preventDefault();
	var $popup = $("#productpopup");
	var popup_url = "/newproduct";
	$(".modal-body", $popup).load(popup_url, function() {
		$popup.modal("show");
	});
};

function editProduct(e, el){
	e.preventDefault();
	var $popup =$("#productpopup");
	var popup_url = $(el).data("url");
	console.log(popup_url);
	$(".modal-body", $popup).load(popup_url, function() {
		$popup.modal("show");
	});
};

function newPayment(e, fn, ln, uid,amnt){
	e.preventDefault();
	$("#payername").text("Skrá innborgun fyrir "+fn+" "+ln);
	if(amnt < 0){
		$("#amount").val(Math.abs(amnt));	
	}
	else{
		$("#amount").val(Math.abs(0));	
	}
	$("#payerid").val(uid);
	$("#userpaymentpopup").modal("show");
};

function editPayment(e, fn, ln, pid, amnt){
	e.preventDefault();
	$("#editpayername").text(fn+" "+ln);
	$("#editamount").val(amnt);
	$("#paymentid").val(pid);
	$("#deletepaymentid").val(pid)
	$("#editpaymentpopup").modal("show");
};

//event,'{{sale.buyer.first_name}}','{{sale.buyer.last_name}}',{{sale.id}},{{sale.price}},'{{sale.product.name|default_if_none:'Vara hætt'}}')
function editSale(e, fn, ln, sid, amnt, pn){
	e.preventDefault();
	$("#editbuyername").text(fn+" "+ln);
	$("#editproduct").val(pn)
	$("#editamount").val(amnt);
	$("#saleid").val(sid);
	$("#deletesaleid").val(sid)
	$("#editsalepopup").modal("show");
};

function newInvite(e){
	e.preventDefault();
	$("#invitepopup").modal("show");
};

function changeStatus(e,t){
	e.preventDefault();
	$(t).closest("form").submit();
};

function productStatus(e,t){
	e.preventDefault();
	val = $("#productactive").val();
	console.log(val);
	if(val == "True"){
		$("#productactivelabel").text("Óvirk");
		$("#productactive").val("False")
	}
	else{
		$("#productactivelabel").text("Virk");
		$("#productactive").val("True")
	}

};

function changeUser(e, id, fn, ln){
	e.preventDefault();
        $("#editfn").val(fn);
        $("#editln").val(ln)
        $("#userid").val(id);
        $("#edituserpopup").modal("show");
}

$(document).ready(purchasedItem);
