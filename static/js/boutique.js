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
	$("#amount").val(Math.abs(amnt));
	$("#payerid").val(uid);
	$("#userpaymentpopup").modal("show");
}

$(document).ready(purchasedItem);
