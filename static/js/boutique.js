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

$(document).ready(purchasedItem);
