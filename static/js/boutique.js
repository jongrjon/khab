function newProduct(e){
	e.preventDefault();
	var $popup = $("#productpopup");
	$popup.modal("show"); 
};

function editProduct(e, id){
	console.log(id)
	e.preventDefault();
};

